"""CLI-Tool-Bench, frozen: the converter, the generated replay and the owner-run freeze script.

Everything here is synthetic: a hand-written `cases.json` for a tiny `greet` tool, and a fake
checkout whose "oracle" is a local git repo. No benchmark data, oracle repo or fuzzer is fetched.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from antstreet.bench import imported
from antstreet.bench.imported import (
    ConvertError,
    convert_clitoolbench,
    fm_match,
    main,
    replay_check,
)
from antstreet.bench.tasks import (
    IMPORTED_SOURCES,
    BenchTask,
    TaskError,
    grade_imported,
    load_task,
    load_tasks,
    task_set_digest,
    validate_task,
)
from antstreet.gate import GateError

ROOT = Path(__file__).resolve().parent.parent
FREEZE = ROOT / "scripts" / "clitoolbench_freeze.py"
COMMIT = "0123456789abcdef0123456789abcdef01234567"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def case(cid: str, command: str, stdout: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": cid,
        "category": extra.pop("category", "BASIC"),
        "command": command,
        "argv": None,
        "stdin": extra.pop("stdin", ""),
        "env": extra.pop("env", {}),
        "prep_script": extra.pop("prep_script", ""),
        "fixtures": extra.pop("fixtures", {}),
        "expected": {
            "exit_code": extra.pop("exit_code", 0),
            "stdout": stdout,
            "fs_delta": extra.pop("fs_delta", {}),
        },
    }


# What the oracle printed and changed, written by hand for a tiny `greet` tool.
CASES = [
    case("c0001", "greet World", "Hello, World!\n"),
    case("c0002", "greet World --shout", "HELLO, WORLD!\n", category="SHOUT"),
    case(
        "c0003",
        "greet Ann -o out.txt",
        "wrote out.txt\n",
        category="OUTPUT",
        fs_delta={
            "out.txt": {
                "type": "ADD",
                "sha256": sha("Hello, Ann!\n"),
                "content": base64.b64encode(b"Hello, Ann!\n").decode(),
            }
        },
    ),
    case(
        "c0004",
        "greet --from {TEST_DATA}/names.txt",
        "Hello, a!\nHello, b!\n",
        fixtures={"names.txt": "a\nb\n"},
    ),
    # No name: usage on stderr, exit 2.
    case("c0005", "greet", "", exit_code=2),
    case(
        "c0006",
        'greet "$(cat {TMP}/n.txt)"',
        "Hello, Zed!\n",
        prep_script="printf Zed > {TMP}/n.txt",
    ),
    # The tool prints its working folder; the replay maps the real path back to the placeholder.
    case("c0007", "greet --where", "{TEST_DATA}\n"),
    case(
        "c0008",
        "greet --rm old.txt",
        "removed\n",
        fixtures={"old.txt": {"base64": base64.b64encode(b"\x00\xff").decode()}},
        fs_delta={"old.txt": {"type": "DEL", "sha256": None}},
    ),
    case("c0009", "printf 'Bo\\n' | greet --stdin", "Hello, Bo!\n", category="STDIN"),
    case("c0010", "greet Al", "Hi, Al!\n", env={"GREETING": "Hi"}),
    # A traceback on stderr, exit 1, nothing else: exactly what `python -m` prints for a missing
    # module. Only the replay's module guard keeps it from passing on an empty product.
    case("c0011", "greet --rm missing.txt", "", exit_code=1),
]
NODE = "tests/test_cases.py::test_case[{}]"

GREET = """import os
import sys


def main(argv):
    greeting = os.environ.get("GREETING", "Hello")
    if not argv:
        print("usage: greet NAME", file=sys.stderr)
        return 2
    if argv[0] == "--where":
        print(os.getcwd())
        return 0
    if argv[0] == "--rm":
        os.remove(argv[1])
        print("removed")
        return 0
    if argv[0] == "--from":
        with open(argv[1]) as f:
            names = f.read().split()
    elif argv[0] == "--stdin":
        names = sys.stdin.read().split()
    else:
        names = [argv[0]]
    lines = [f"{greeting}, {n}!" for n in names]
    if "--shout" in argv:
        lines = [SHOUT(line) for line in lines]
    if "-o" in argv:
        out = argv[argv.index("-o") + 1]
        with open(out, "w") as f:
            f.write(FILE_TEXT)
        print(f"wrote {out}")
        return 0
    print("\\n".join(lines))
    return 0


sys.exit(main(sys.argv[1:]))
"""
RIGHT = GREET.replace("SHOUT(line)", "line.upper()").replace(
    "FILE_TEXT", '"\\n".join(lines) + "\\n"'
)
# Wrong twice: shouting lower-cases, and the file written by -o lacks its newline. The second is
# caught only by the filesystem delta: its stdout ("wrote out.txt") is right.
WRONG = GREET.replace("SHOUT(line)", "line.lower()").replace("FILE_TEXT", '"\\n".join(lines)')


def frozen(
    root: Path, cases: list[dict[str, Any]] | None = None, task: str = "acme/greet", **top: Any
) -> Path:
    src = root / task.replace("/", "__")
    src.mkdir(parents=True, exist_ok=True)
    cases = CASES if cases is None else cases
    data: dict[str, Any] = {
        "format": "antstreet-clitoolbench-frozen/1",
        "task": task,
        "seed": 0,
        "cases_per_task": len(cases),
        "oracle": {
            "url": "https://github.com/acme/greet.git",
            "commit": COMMIT,
            "licence": "MIT License",
            "python": "3.12.7",
            "deps": [],
            "programs": ["greet"],
        },
        "flags": [],
        "dropped": [],
        "cases": cases,
    }
    data.update(top)
    (src / "cases.json").write_text(json.dumps(data))
    (src / "spec.md").write_text("# greet\n\nA CLI that greets people.\n")
    return src


def product(root: Path, source: str | None, name: str = "prod") -> Path:
    folder = root / name
    (folder / "greet").mkdir(parents=True)
    if source is not None:
        (folder / "greet" / "__main__.py").write_text(source)
    return folder


@pytest.fixture
def task(tmp_path: Path) -> BenchTask:
    return load_task(convert_clitoolbench(frozen(tmp_path), tmp_path / "tasks"))


def problems(task: BenchTask) -> list[str]:
    with pytest.raises(TaskError) as info:
        validate_task(task)
    return info.value.problems


# --- the converter ---------------------------------------------------------------------------


def test_the_converter_writes_an_imported_task_that_validates(task: BenchTask) -> None:
    assert "clitoolbench" in IMPORTED_SOURCES
    assert (task.id, task.difficulty) == ("clitb-greet", "hard")
    assert task.imported is not None
    assert (task.imported.source, task.imported.test_path, task.imported.test_count) == (
        "clitoolbench",
        "tests",
        len(CASES),
    )
    assert task.idea.startswith("# greet\n\nA CLI that greets people.")
    for term in ("python -m greet", "standard library only", "stderr is not compared"):
        assert term in task.idea
    provenance = json.loads((task.root / "provenance.json").read_text())
    assert provenance["oracle"]["commit"] == COMMIT and provenance["stdout_match"] == "em"
    validate_task(task)  # empty product passes nothing; the parametrized suite is collected


def test_the_empty_product_fails_every_case_including_a_silent_error_case(
    task: BenchTask, tmp_path: Path
) -> None:
    # c0011 expects exit 1 and no output; the module guard makes it fail on a missing product.
    hidden = grade_imported(task, product(tmp_path, None))
    assert len(hidden) == len(CASES) and set(hidden.values()) == {"failed"}


def test_a_right_product_passes_every_case_through_the_real_gate(
    task: BenchTask, tmp_path: Path
) -> None:
    hidden = grade_imported(task, product(tmp_path, RIGHT))
    assert hidden == {NODE.format(c["id"]): "passed" for c in CASES}


def test_a_wrong_product_fails_exactly_the_cases_it_gets_wrong(
    task: BenchTask, tmp_path: Path
) -> None:
    hidden = grade_imported(task, product(tmp_path, WRONG))
    failed = {n for n, s in hidden.items() if s != "passed"}
    assert failed == {NODE.format("c0002"), NODE.format("c0003")}


def test_a_wrong_exit_code_fails_even_when_the_output_is_right(
    task: BenchTask, tmp_path: Path
) -> None:
    exits_one = RIGHT.replace("sys.exit(main(sys.argv[1:]))", "main(sys.argv[1:])\nsys.exit(1)")
    hidden = grade_imported(task, product(tmp_path, exits_one))
    # Only the case whose oracle exited 1 passes.
    assert {n for n, s in hidden.items() if s == "passed"} == {NODE.format("c0011")}


def test_the_spec_shows_the_launcher_and_the_stdlib_rule_and_never_the_cases(
    task: BenchTask,
) -> None:
    for c in CASES:
        assert len(c["command"]) < 6 or c["command"] not in task.idea
    assert "Hello, World!" not in task.idea and "{TEST_DATA}" not in task.idea
    assert "c0001" not in task.idea and "cases.json" not in task.idea


# --- FM ------------------------------------------------------------------------------------------


def test_fm_threshold_is_inclusive_at_eighty_percent() -> None:
    # Levenshtein (indel) ratio = 2 * LCS / (len(a) + len(b)).
    assert fm_match("abcde", "abcdf")  # LCS 4, 8/10 = 0.80 exactly: passes
    assert not fm_match("abcdefghi", "abcdefgXY")  # LCS 7, 14/18 = 0.78: fails
    assert fm_match("", "")
    assert not fm_match("", "x")
    assert fm_match("same", "same")


def test_fm_falls_back_to_exact_above_its_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imported, "FM_MAX_CHARS", 4)
    assert not fm_match("abcde", "abcdf")
    assert fm_match("abcde", "abcde")


def test_fm_tasks_grade_near_misses_as_passes_and_em_tasks_do_not(tmp_path: Path) -> None:
    near = RIGHT.replace('f"{greeting}, {n}!"', 'f"{greeting}, {n}!!"')
    one = [CASES[0]]
    em = load_task(convert_clitoolbench(frozen(tmp_path / "a", one), tmp_path / "t"))
    fm = load_task(
        convert_clitoolbench(frozen(tmp_path / "b", one), tmp_path / "t2", stdout_match="fm")
    )
    folder = product(tmp_path, near)
    assert grade_imported(em, folder) == {NODE.format("c0001"): "failed"}
    assert grade_imported(fm, folder) == {NODE.format("c0001"): "passed"}
    assert json.loads((fm.root / "provenance.json").read_text())["stdout_match"] == "fm"
    with pytest.raises(ConvertError, match="stdout_match"):
        convert_clitoolbench(frozen(tmp_path / "c", one), tmp_path / "t3", stdout_match="sm")


# --- malformed input is refused --------------------------------------------------------------


def bad(cid: str = "c0001", **change: Any) -> list[dict[str, Any]]:
    c = json.loads(json.dumps(CASES[0]))
    for key, value in change.items():
        target = c["expected"] if key in ("exit_code", "stdout", "fs_delta") else c
        target[key] = value
    c["id"] = cid
    return [c]


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        (bad(fixtures={"../escape.txt": "x"}), "fixture"),
        (bad(fixtures={"/etc/passwd": "x"}), "fixture"),
        (bad(fixtures={"a/./b": "x"}), "fixture"),
        (bad(fixtures={"a\\b": "x"}), "fixture"),
        (bad(fs_delta={"../out": {"type": "ADD", "sha256": "0" * 64}}), "fs_delta"),
        (bad(fs_delta={"x": {"type": "ADD", "sha256": "nothex"}}), "fs_delta"),
        (bad(fs_delta={"x": {"type": "MOVE", "sha256": "0" * 64}}), "fs_delta"),
        (bad(exit_code=256), "exit_code"),
        (bad(exit_code=True), "exit_code"),
        (bad(stdout="x" * (64 * 1024 + 1)), "stdout"),
        (bad(command=""), "command"),
        (bad(command="greet\x00"), "command"),
        (bad(env={"PATH": "/evil"}), "env"),
        (bad(env={"PYTHONPATH": "/evil"}), "env"),
        (bad(cid="../c1"), "id"),
        (bad(fixtures={"big": "x" * (1024 * 1024 + 1)}), "fixture"),
        ([], "cases"),
        (bad() + bad(), "duplicate"),
    ],
)
def test_malformed_cases_are_refused_and_nothing_is_written(
    tmp_path: Path, cases: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ConvertError, match=message):
        convert_clitoolbench(frozen(tmp_path, cases), tmp_path / "tasks")
    assert not (tmp_path / "tasks").exists()


@pytest.mark.parametrize(
    ("top", "message"),
    [
        ({"format": "something-else/1"}, "format"),
        ({"task": "../../x"}, "task"),
        ({"seed": "0"}, "seed"),
        ({"oracle": {"url": "https://x", "commit": "abc"}}, "oracle"),
        (
            {
                "oracle": {
                    "url": "https://github.com/acme/greet.git",
                    "commit": COMMIT,
                    "licence": "MIT",
                    "python": "3.12",
                    "deps": [],
                    "programs": ["greet;rm -rf ~"],
                }
            },
            "program",
        ),
    ],
)
def test_a_malformed_frozen_header_is_refused(
    tmp_path: Path, top: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConvertError, match=message):
        convert_clitoolbench(frozen(tmp_path, **top), tmp_path / "tasks")


def test_an_oversized_or_unparseable_cases_file_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = frozen(tmp_path)
    monkeypatch.setattr(imported, "FROZEN_MAX_BYTES", 100)
    with pytest.raises(ConvertError, match="larger than"):
        convert_clitoolbench(src, tmp_path / "tasks")
    monkeypatch.undo()
    (src / "cases.json").write_text("{not json")
    with pytest.raises(ConvertError, match="not valid JSON"):
        convert_clitoolbench(src, tmp_path / "tasks")
    (src / "cases.json").unlink()
    (src / "skipped.json").write_text('{"reason": "oracle 404"}')
    with pytest.raises(ConvertError, match="skipped"):
        convert_clitoolbench(src, tmp_path / "tasks")


def test_a_symlinked_cases_file_is_refused(tmp_path: Path) -> None:
    src = frozen(tmp_path)
    real = tmp_path / "elsewhere.json"
    (src / "cases.json").rename(real)
    (src / "cases.json").symlink_to(real)
    with pytest.raises(ConvertError, match="symlink"):
        convert_clitoolbench(src, tmp_path / "tasks")


def test_an_oracle_with_third_party_deps_is_flagged(tmp_path: Path, capsys: Any) -> None:
    oracle = {
        "url": "https://github.com/acme/greet.git",
        "commit": COMMIT,
        "licence": "MIT",
        "python": "3.12.7",
        "deps": ["click==8.1.7"],
        "programs": ["greet"],
    }
    src = frozen(tmp_path, oracle=oracle, flags=["custom_stdout_sanitizer"])
    assert main(["clitoolbench", str(src), str(tmp_path / "t")]) == 0
    err = capsys.readouterr().err
    assert "click==8.1.7" in err and "custom_stdout_sanitizer" in err
    provenance = json.loads((tmp_path / "t" / "clitb-greet" / "provenance.json").read_text())
    assert "oracle_needs_third_party" in provenance["flags"]


def test_the_case_count_must_be_the_freeze_s_fixed_n(tmp_path: Path) -> None:
    with pytest.raises(ConvertError, match="cases_per_task says 50"):
        convert_clitoolbench(frozen(tmp_path, cases_per_task=50), tmp_path / "tasks")


def test_recorded_file_content_must_hash_to_its_sha256_and_stays_out_of_the_hidden_tree(
    tmp_path: Path, task: BenchTask
) -> None:
    hidden = json.loads((task.hidden_dir / "cases.json").read_text())
    assert all(
        "content" not in c for x in hidden["cases"] for c in x["expected"]["fs_delta"].values()
    )
    lying = {"type": "ADD", "sha256": sha("other\n"), "content": base64.b64encode(b"x").decode()}
    with pytest.raises(ConvertError, match="does not hash"):
        convert_clitoolbench(frozen(tmp_path / "a", bad(fs_delta={"o": lying})), tmp_path / "t")
    broken = {"type": "ADD", "sha256": sha("x"), "content": "%%%"}
    with pytest.raises(ConvertError, match="not base64"):
        convert_clitoolbench(frozen(tmp_path / "b", bad(fs_delta={"o": broken})), tmp_path / "t")


# --- replay validation -----------------------------------------------------------------------


def test_the_recorded_outputs_replayed_pass_every_case_the_playback_can_identify(
    task: BenchTask, tmp_path: Path
) -> None:
    report = replay_check(task, frozen(tmp_path / "src"))
    # c0006 passes its name through "$(cat ...)": the playback cannot know its arguments.
    assert report.unverified == ("c0006",)
    assert set(report.verified) == {c["id"] for c in CASES} - {"c0006"}
    assert report.failed == () and report.problem is None
    assert 0 < report.seconds < imported.REPLAY_MAX_S == 90


def test_a_replay_slower_than_half_the_suite_cap_drops_the_task(
    task: BenchTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(imported, "REPLAY_MAX_S", 0.0)
    problem = replay_check(task, frozen(tmp_path / "src")).problem
    assert problem is not None and "the replay took" in problem


# Same command, same files, two different recorded outputs: no product can pass both.
TWINS = [
    case("c0001", "greet World", "Hello, World!\n"),
    case("c0002", "greet World", "Goodbye, World!\n"),
]


def test_recorded_outputs_no_product_can_reach_drop_the_task(tmp_path: Path) -> None:
    src = frozen(tmp_path / "src", TWINS)
    task = load_task(convert_clitoolbench(src, tmp_path / "t"))
    report = replay_check(task, src)
    assert report.failed == ("c0001", "c0002")  # ambiguous: the playback answers neither
    assert report.problem is not None and "no product can pass" in report.problem


def freeze_output(root: Path) -> Path:
    out = root / "freeze"
    frozen(out)
    frozen(out, TWINS, task="acme/twins")
    (out / "acme__gone").mkdir()
    (out / "acme__gone" / "skipped.json").write_text('{"reason": "oracle install failed"}')
    index = {
        "format": "antstreet-clitoolbench-frozen/1",
        "seed": 0,
        "cases_per_task": 11,
        "python": "3.12.7",
        "frozen": ["acme/greet", "acme/twins"],
        "skipped": {"acme/gone": "oracle install failed: Exception: Oracle Installation Failed"},
    }
    (out / "index.json").write_text(json.dumps(index))
    return out


def test_convert_all_keeps_what_passes_and_the_manifest_says_why_the_rest_went(
    tmp_path: Path, capsys: Any
) -> None:
    dest = tmp_path / "pool"
    assert main(["clitoolbench", str(freeze_output(tmp_path)), str(dest), "--all"]) == 0
    out = capsys.readouterr().out
    assert "kept acme/greet as clitb-greet" in out and "dropped acme/twins at replay" in out
    assert sorted(p.name for p in dest.iterdir()) == ["clitb-greet", "clitoolbench-manifest.json"]
    manifest = json.loads((dest / "clitoolbench-manifest.json").read_text())
    assert (manifest["seed"], manifest["cases_per_task"], manifest["freeze_python"]) == (
        0,
        11,
        "3.12.7",
    )
    [kept] = manifest["kept"]
    assert kept["oracle"]["commit"] == COMMIT and kept["replay_unverified"] == ["c0006"]
    stages = {row["task"]: row["stage"] for row in manifest["dropped"]}
    assert stages == {"acme/gone": "freeze", "acme/twins": "replay"}
    assert [t.id for t in load_tasks(dest)] == ["clitb-greet"]
    # The pre-registration digest covers the manifest.
    before = task_set_digest(dest)
    (dest / "clitoolbench-manifest.json").write_text(json.dumps({**manifest, "kept": []}))
    assert task_set_digest(dest) != before
    assert main(["clitoolbench", str(tmp_path / "freeze"), str(dest), "--all"]) == 1


def test_method_documents_the_frozen_clitoolbench() -> None:
    text = (ROOT / "bench" / "METHOD.md").read_text()
    body = text.split("## CLI-Tool-Bench (frozen)")[1].split("\n## ")[0]
    for term in (
        "scripts/clitoolbench_freeze.sh",
        "python -m antstreet.bench.imported clitoolbench",
        "SM",
        "LICENSE",
        "seed",
        "0.8",
        "--all",
        "clitoolbench-manifest.json",
        "N = 50",
        "flaky",
        "90 s",
        "not vendored",
        "accident guard",
        "only boundary",
        "T12",
        "--network none",
        "--cap-drop ALL",
        "--image-digest",
        "setup.py",
    ):
        assert term in body


# --- the freeze script -----------------------------------------------------------------------


def load_freeze() -> Any:
    spec = importlib.util.spec_from_file_location("clitoolbench_freeze", FREEZE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_freeze_script_refuses_to_run_outside_its_container(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "CLITOOLBENCH_IN_CONTAINER"}
    done = subprocess.run(
        [sys.executable, "-I", str(FREEZE), "--phase", "install", str(tmp_path / "bench")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert "inside its Docker container" in done.stderr
    assert not (tmp_path / "out").exists()


def test_the_freeze_script_and_the_replay_agree_on_ansi_and_harness_variables() -> None:
    freeze = load_freeze()
    assert freeze.ANSI_PATTERN == imported.ANSI_PATTERN
    assert freeze.HARNESS_ENV == imported._HARNESS_ENV


def test_the_freeze_script_lists_the_34_python_tasks() -> None:
    tasks = load_freeze().PYTHON_TASKS
    assert len(tasks) == len(set(tasks)) == 34 and "simonw/files-to-prompt" in tasks


FAKE_BASE = """import random
from dataclasses import dataclass, field


@dataclass
class TestCase:
    command: str
    category: str = "UNKNOWN"
    prep_script: str = ""
    mount_files: dict = field(default_factory=dict)
    env_vars: dict = field(default_factory=dict)


class BaseRepoAdapter:
    repo_root_dir = "/repo"
    test_data_dir = "/test_data"

    def sanitize_stdout(self, raw):
        return raw


class FuzzHelper:
    @staticmethod
    def get_string(a=5, b=20):
        return "".join(random.choice("abcdefgh") for _ in range(random.randint(a, b)))
"""
FAKE_START = """import os, random, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from BaseRepoAdapter import BaseRepoAdapter, TestCase, FuzzHelper
from DiffTestEngine import DiffTestEngine


class GreetAdapter(BaseRepoAdapter):
    test_data_dir = @TD@
    repo_root_dir = @REPO@

    @property
    def base_image(self):
        return "python:latest"

    def install_oracle(self, container):
        # Into the shared repo root, as upstream adapters do: every task's clone lands there.
        r = container.exec_run("git clone @ORIGIN@ @REPOPATH@/greet")
        if r.exit_code != 0:
            raise Exception("Oracle Installation Failed")
        @INSTALL_EXTRA@
        copy = 'cp @REPOPATH@/greet/greet.sh "$VIRTUAL_ENV/bin/greet"'
        copy += ' && chmod +x "$VIRTUAL_ENV/bin/greet"'
        r = container.exec_run(["sh", "-c", copy])
        if r.exit_code != 0:
            raise Exception("Oracle Installation Failed")

    def generate_test_cases(self):
        cases = []
        for _ in range(30):
            name = FuzzHelper.get_string(3, 6)
            cases.append(TestCase(command=f"greet {name}", category="BASIC"))
            cases.append(TestCase(command="greet --from @TD@/names.txt", category="FILE",
                                  mount_files={"names.txt": "x\\ny\\n"}))
        cases.append(TestCase(command="greet Ann -o out.txt", category="OUTPUT"))
        @EXTRA@
        cases.append(TestCase(command="greet x > @REPOPATH@/x", category="REPO"))
        return cases


if __name__ == "__main__":
    raise SystemExit("the engine must never run")
"""
FAKE_ORACLE_SH = """#!/bin/sh
case "$1" in
  --from) while read -r n; do echo "Hello, $n!"; done < "$2" ;;
  *) if [ "$2" = "-o" ]; then echo "Hello, $1!" > "$3"; echo "wrote $3";
     else echo "Hello, $1!"; fi ;;
esac
"""


def fake_checkout(tmp_path: Path) -> Path:
    origin = tmp_path / "origin"
    origin.mkdir()
    (origin / "greet.sh").write_text(FAKE_ORACLE_SH)
    (origin / "LICENSE").write_text("\nMIT License\n\nCopyright ...\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-C", str(origin)]
    for args in (["init", "-q"], ["add", "."], ["commit", "-qm", "oracle"]):
        subprocess.run([*git, *args], check=True, capture_output=True)
    bench, td, repo = tmp_path / "bench", tmp_path / "td", tmp_path / "repo-root"
    repo.mkdir()
    locked = tmp_path / "locked"
    locked.mkdir(mode=0o500)
    write_locked = f'container.exec_run(["sh", "-c", "touch {locked}/x"])'
    run = bench / "run_differential_test"
    # `$$` is the shell's pid: a different greeting on every run, so that task is flaky.
    flaky = 'cases.append(TestCase(command="greet $$", category="CLOCK"))'
    for owner_repo, start in (
        ("acme/greet", FAKE_START.replace("@EXTRA@", "")),
        ("acme/gone", FAKE_START.replace("@ORIGIN@", str(tmp_path / "missing"))),
        ("acme/flaky", FAKE_START.replace("@EXTRA@", flaky)),
        (
            "acme/locked",
            FAKE_START.replace(
                "@INSTALL_EXTRA@",
                write_locked + "\n        raise Exception('Oracle Installation Failed')",
            ),
        ),
        (
            "acme/ro-data",
            FAKE_START.replace("test_data_dir = @TD@", f"test_data_dir = {str(locked / 'td')!r}"),
        ),
    ):
        (run / "repo" / owner_repo).mkdir(parents=True)
        source = (
            start.replace("@ORIGIN@", str(origin))
            .replace("@EXTRA@", "")
            .replace("@INSTALL_EXTRA@", "")
            .replace("@REPOPATH@", str(repo))
            .replace("@REPO@", repr(str(repo)))
            .replace("@TD@", repr(str(td)), 1)
            .replace("@TD@", str(td))
        )
        (run / "repo" / owner_repo / "start.py").write_text(source)
        (bench / "agent_prompt" / owner_repo).mkdir(parents=True)
        (bench / "agent_prompt" / owner_repo / "agent_prompt.txt").write_text("Build greet.\n")
    (run / "BaseRepoAdapter.py").write_text(FAKE_BASE)
    return bench


DIGEST = "sha256:" + "ab" * 32


def run_freeze(tmp_path: Path, name: str, *args: str) -> Path:
    """Both phases, as the two containers run them: install, then run on the same work folder."""
    bench, out = tmp_path / "bench", tmp_path / name
    env = {**os.environ, "CLITOOLBENCH_IN_CONTAINER": "1"}
    common = [str(bench), "--work", str(tmp_path / f"work-{name}"), "--venv-without-pip", *args]
    for phase in (["--phase", "install"], ["--phase", "run", "--out", str(out)]):
        argv = [sys.executable, "-I", str(FREEZE), *phase, "--image-digest", DIGEST, *common]
        done = subprocess.run(argv, env=env, capture_output=True, text=True, check=False)
        assert done.returncode == 0, done.stderr
    return out


@pytest.mark.skipif(shutil.which("git") is None, reason="the fake oracle is a local git repo")
def test_the_freeze_script_freezes_a_fake_oracle_deterministically(tmp_path: Path) -> None:
    fake_checkout(tmp_path)
    origin_head = subprocess.run(
        ["git", "-C", str(tmp_path / "origin"), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tasks = ["--task", "acme/greet", "--task", "acme/gone", "--task", "acme/flaky"]
    outs = [run_freeze(tmp_path, f"out{n}", *tasks, "--cases-per-task", "5") for n in (1, 2)]
    data = json.loads((outs[0] / "acme__greet" / "cases.json").read_text())
    assert (outs[1] / "acme__greet" / "cases.json").read_text() == (
        outs[0] / "acme__greet" / "cases.json"
    ).read_text()
    assert (data["seed"], data["cases_per_task"], len(data["cases"])) == (0, 5, 5)
    assert data["oracle"]["commit"] == origin_head
    assert data["oracle"]["licence"] == "MIT License" and data["oracle"]["programs"] == ["greet"]
    # Round robin over categories: BASIC, FILE, OUTPUT, (REPO dropped), BASIC, BASIC. The FILE
    # case is the same 30 times, so it is there once.
    assert [c["category"] for c in data["cases"]] == ["BASIC", "FILE", "OUTPUT", "BASIC", "BASIC"]
    assert data["dropped"] == [
        {
            "category": "REPO",
            "reason": "touches the oracle's install folder, which the product does not have",
        }
    ]
    file_case = next(c for c in data["cases"] if c["category"] == "FILE")
    assert file_case["command"] == "greet --from {TEST_DATA}/names.txt"
    assert file_case["expected"]["stdout"] == "Hello, x!\nHello, y!\n"
    out_case = next(c for c in data["cases"] if c["category"] == "OUTPUT")
    assert out_case["expected"]["fs_delta"] == {
        "out.txt": {
            "type": "ADD",
            "sha256": sha("Hello, Ann!\n"),
            "content": base64.b64encode(b"Hello, Ann!\n").decode(),
        }
    }
    gone = json.loads((outs[0] / "acme__gone" / "skipped.json").read_text())
    assert "Oracle Installation Failed" in gone["reason"]
    flaky = json.loads((outs[0] / "acme__flaky" / "skipped.json").read_text())
    assert flaky["reason"].startswith("flaky: two runs of the oracle differed on 'CLOCK'")
    index = json.loads((outs[0] / "index.json").read_text())
    assert index["frozen"] == ["acme/greet"]
    assert sorted(index["skipped"]) == ["acme/flaky", "acme/gone"]
    assert index["cases_per_task"] == 5 and index["python"].startswith("3.")
    # Freeze -> convert, validate and replay -> grade.
    pool = tmp_path / "pool"
    manifest = imported.convert_clitoolbench_all(outs[0], pool)
    assert [k["id"] for k in manifest["kept"]] == ["clitb-greet"]
    assert manifest["kept"][0]["replay_unverified"] == []
    assert {d["task"] for d in manifest["dropped"]} == {"acme/gone", "acme/flaky"}
    task = load_task(pool / "clitb-greet")
    assert set(grade_imported(task, product(tmp_path, RIGHT)).values()) == {"passed"}
    graded = grade_imported(task, product(tmp_path, WRONG, "wrong"))
    assert {n for n, s in graded.items() if s == "failed"} == {NODE.format(out_case["id"])}


@pytest.mark.skipif(shutil.which("git") is None, reason="the fake oracle is a local git repo")
def test_a_task_short_of_the_fixed_n_is_skipped_not_frozen_smaller(tmp_path: Path) -> None:
    fake_checkout(tmp_path)
    out = run_freeze(tmp_path, "out", "--task", "acme/greet", "--cases-per-task", "500")
    skipped = json.loads((out / "acme__greet" / "skipped.json").read_text())
    assert re.fullmatch(r"only \d+ of 500 cases could be frozen", skipped["reason"])
    assert not (out / "acme__greet" / "cases.json").exists()


def test_the_stdout_audit_blames_third_party_text_and_not_the_oracle_s_own(
    tmp_path: Path,
) -> None:
    freeze = load_freeze()
    hook, deps, log = tmp_path / "hook", tmp_path / "deps", tmp_path / "audit.log"
    hook.mkdir()
    deps.mkdir()
    (hook / "sitecustomize.py").write_text(freeze.AUDIT_HOOK)
    (deps / "fancy.py").write_text(
        "import sys\n\ndef banner():\n    sys.stdout.write('*** fancy ***\\n')\n"
    )
    (deps / "click.py").write_text("import sys\n\ndef echo(m):\n    sys.stdout.write(m + '\\n')\n")
    tool = tmp_path / "tool.py"
    tool.write_text(
        "import click, fancy\nprint('own text')\nfancy.banner()\nclick.echo('passed through')\n"
    )
    env = {**os.environ, "PYTHONPATH": f"{hook}{os.pathsep}{deps}", "CLITB_STDOUT_AUDIT": str(log)}
    done = subprocess.run(
        [sys.executable, str(tool)], env=env, capture_output=True, text=True, check=True
    )
    assert done.stdout == "own text\n*** fancy ***\npassed through\n"  # the hook changes nothing
    records = freeze._audit_records(log)
    assert {r[1] for r in records} >= {"<module>", "banner", "echo"}
    dep_files = {
        str((deps / "fancy.py").resolve()): "fancy==1.0",
        str((deps / "click.py").resolve()): "click==8.1.7",
    }
    assert freeze.dep_evidence(records, dep_files) == [
        {
            "dep": "fancy==1.0",
            "file": str(deps / "fancy.py"),
            "function": "banner",
            "sample": "*** fancy ***\n",
        }
    ]
    assert freeze.dep_evidence(records, {}) == []  # no third-party package, no evidence


# --- the sandbox is never optional for imported tasks ----------------------------------------


@pytest.fixture
def no_sandbox(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """No working sandbox tool on this machine, and the user asked for none; any run of the
    hidden tree is recorded (it must never happen)."""
    import antstreet.gate as gate_module
    from antstreet import sandbox

    monkeypatch.setattr(sandbox, "detect", lambda *a, **k: None)
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "off")
    ran: list[object] = []
    monkeypatch.setattr(
        gate_module, "_run_bounded", lambda *a, **k: ran.append(a) or (0, "", False)
    )
    return ran


def test_grading_refuses_without_a_sandbox_and_runs_nothing(
    task: BenchTask, tmp_path: Path, no_sandbox: list[object]
) -> None:
    with pytest.raises(GateError, match="sandbox"):
        grade_imported(task, product(tmp_path, RIGHT))
    with pytest.raises(GateError, match="sandbox"):
        validate_task(task)
    with pytest.raises(GateError, match="sandbox"):
        replay_check(task, frozen(tmp_path / "src"))
    assert no_sandbox == []


def test_an_nl2repo_task_is_refused_without_a_sandbox_too(
    tmp_path: Path, no_sandbox: list[object]
) -> None:
    from test_bench_imported import UPPER, make_source
    from test_bench_imported import product as nl2repo_product

    from antstreet.bench.imported import convert_nl2repo

    nl2repo = load_task(convert_nl2repo(make_source(tmp_path), tmp_path / "tasks"))
    with pytest.raises(GateError, match="sandbox"):
        grade_imported(nl2repo, nl2repo_product(tmp_path, UPPER))
    assert no_sandbox == []


def test_off_in_the_environment_does_not_turn_the_sandbox_off_for_imported_tasks(
    task: BenchTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "off")
    report = replay_check(task, frozen(tmp_path / "src"))
    assert report.sandboxed and report.problem is None


def test_a_tree_run_that_reports_unsandboxed_is_refused(
    task: BenchTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import antstreet.bench.tasks as tasks_module
    from antstreet.gate import TreeResult

    def unsandboxed(*args: object, **kwargs: object) -> TreeResult:
        return TreeResult({}, 0, "ran", "", 0.1, False, ())

    monkeypatch.setattr(tasks_module, "run_tree", unsandboxed)
    with pytest.raises(GateError, match="not sandboxed"):
        grade_imported(task, product(tmp_path, RIGHT))


# --- the freeze output is untrusted: no symlinks, no special files, bounded, cleaned ----------

SECRET = "FAKE-SECRET-TOKEN-123"


def planted_secret(tmp_path: Path) -> Path:
    secret = tmp_path / "home" / ".ssh" / "id_fake"
    secret.parent.mkdir(parents=True)
    secret.write_text(f"{SECRET}\n")
    return secret


def test_a_symlinked_skipped_json_is_refused_and_its_target_never_read(
    tmp_path: Path, capsys: Any
) -> None:
    src = frozen(tmp_path / "freeze")
    (src / "skipped.json").symlink_to(planted_secret(tmp_path))
    with pytest.raises(ConvertError, match="symlink") as info:
        convert_clitoolbench(src, tmp_path / "t")
    assert SECRET not in str(info.value)
    assert main(["clitoolbench", str(src), str(tmp_path / "t2")]) == 1
    assert SECRET not in capsys.readouterr().err


def test_special_files_in_a_frozen_task_are_refused_without_being_read(tmp_path: Path) -> None:
    src = frozen(tmp_path / "a")
    (src / "skipped.json").symlink_to("/dev/zero")
    with pytest.raises(ConvertError, match="symlink"):
        convert_clitoolbench(src, tmp_path / "t")
    fifo_task = frozen(tmp_path / "b")
    (fifo_task / "cases.json").unlink()
    os.mkfifo(fifo_task / "cases.json")  # reading it would block forever
    with pytest.raises(ConvertError, match="special file: cases.json"):
        convert_clitoolbench(fifo_task, tmp_path / "t")
    # The reader itself never follows a link or blocks on a fifo, even if the tree check raced.
    with pytest.raises(ConvertError, match="not a regular file"):
        imported._read_bounded(fifo_task / "cases.json", 100)
    with pytest.raises(ConvertError, match="symlink"):
        imported._read_bounded(src / "skipped.json", 100)
    with pytest.raises(ConvertError, match="cannot read"):
        imported._read_bounded(tmp_path / "missing.json", 100)
    (tmp_path / "latin1.json").write_bytes(b"\xff\xfe")
    with pytest.raises(ConvertError, match="not UTF-8"):
        imported._read_bounded(tmp_path / "latin1.json", 100)
    nested = frozen(tmp_path / "c")
    (nested / "extra").mkdir()
    (nested / "extra" / "link").symlink_to(planted_secret(tmp_path / "c"))
    with pytest.raises(ConvertError, match="extra/link"):
        convert_clitoolbench(nested, tmp_path / "t")


def test_a_real_skipped_json_gives_only_a_short_clean_reason(tmp_path: Path) -> None:
    src = frozen(tmp_path)
    (src / "cases.json").unlink()
    reason = "\x1b]0;owned\x07oracle 404 " + "x" * 5000
    (src / "skipped.json").write_text(json.dumps({"reason": reason, "other": SECRET}))
    with pytest.raises(ConvertError) as info:
        convert_clitoolbench(src, tmp_path / "t")
    message = str(info.value)
    assert "oracle 404" in message and SECRET not in message
    assert "\x1b" not in message and "\x07" not in message and len(message) < 600
    (src / "skipped.json").write_text("x" * (64 * 1024 + 1))
    with pytest.raises(ConvertError, match="larger than"):
        convert_clitoolbench(src, tmp_path / "t")


def test_convert_all_drops_a_task_holding_a_symlink_and_leaks_nothing(
    tmp_path: Path, capsys: Any
) -> None:
    out = freeze_output(tmp_path)
    leak = frozen(out, task="acme/leak")
    (leak / "skipped.json").symlink_to(planted_secret(tmp_path))
    dest = tmp_path / "pool"
    assert main(["clitoolbench", str(out), str(dest), "--all"]) == 0
    printed = capsys.readouterr().out
    manifest_text = (dest / "clitoolbench-manifest.json").read_text()
    assert SECRET not in printed and SECRET not in manifest_text
    dropped = {r["task"]: r for r in json.loads(manifest_text)["dropped"]}
    assert "symlink" in dropped["acme__leak"]["reason"]
    assert not list(dest.glob("staging-*"))


def test_a_top_level_symlink_refuses_the_whole_run(tmp_path: Path, capsys: Any) -> None:
    out = freeze_output(tmp_path)
    (out / "acme__planted").symlink_to(tmp_path / "home", target_is_directory=True)
    assert main(["clitoolbench", str(out), str(tmp_path / "pool"), "--all"]) == 1
    assert "symlink" in capsys.readouterr().err
    assert not (tmp_path / "pool" / "clitoolbench-manifest.json").exists()


def test_a_deeply_nested_json_is_a_clean_refusal_not_a_traceback(
    tmp_path: Path, capsys: Any
) -> None:
    out = freeze_output(tmp_path)
    (out / "acme__twins" / "cases.json").write_text("[" * 200_000)
    dest = tmp_path / "pool"
    assert main(["clitoolbench", str(out), str(dest), "--all"]) == 0
    dropped = {
        r["task"]: r
        for r in json.loads((dest / "clitoolbench-manifest.json").read_text())["dropped"]
    }
    assert "not valid JSON" in dropped["acme__twins"]["reason"]
    assert not list(dest.glob("staging-*"))
    (out / "index.json").write_text("[" * 200_000)
    assert main(["clitoolbench", str(out), str(tmp_path / "pool2"), "--all"]) == 1
    assert "not valid JSON" in capsys.readouterr().err
    assert not (tmp_path / "pool2").exists() or not list((tmp_path / "pool2").iterdir())


def test_every_reason_in_the_manifest_and_on_screen_is_short_and_clean(
    tmp_path: Path, capsys: Any
) -> None:
    out = freeze_output(tmp_path)
    index = json.loads((out / "index.json").read_text())
    index["skipped"]["acme/gone"] = "\x1b[2J\x1b]0;title\x07" + "y" * 5000
    (out / "index.json").write_text(json.dumps(index))
    dest = tmp_path / "pool"
    assert main(["clitoolbench", str(out), str(dest), "--all"]) == 0
    printed = capsys.readouterr().out
    manifest = json.loads((dest / "clitoolbench-manifest.json").read_text())
    for row in manifest["dropped"]:
        assert len(row["reason"]) <= 300 and not re.search(r"[\x00-\x1f\x7f]", row["reason"])
    assert "\x1b" not in printed and "\x07" not in printed


@pytest.mark.skipif(shutil.which("git") is None, reason="the fake oracle is a local git repo")
def test_an_adapter_that_needs_another_writable_path_is_skipped_loudly(
    tmp_path: Path,
) -> None:
    fake_checkout(tmp_path)
    out = run_freeze(tmp_path, "out", "--task", "acme/locked", "--task", "acme/ro-data")
    locked = json.loads((out / "acme__locked" / "skipped.json").read_text())
    assert locked["reason"].startswith("the install needs a writable path outside /repo")
    assert "last failing command 'sh -c touch" in locked["reason"]
    ro_data = json.loads((out / "acme__ro-data" / "skipped.json").read_text())
    assert ro_data["reason"].startswith(f"needs a writable {tmp_path / 'locked' / 'td'}")
    # Whatever happened, the shared repo root is empty again for the next task.
    assert list((tmp_path / "repo-root").iterdir()) == []


def test_phase_run_refuses_without_an_image_digest(tmp_path: Path) -> None:
    (tmp_path / "bench" / "run_differential_test").mkdir(parents=True)
    env = {**os.environ, "CLITOOLBENCH_IN_CONTAINER": "1"}
    argv = [sys.executable, "-I", str(FREEZE), "--phase", "run", str(tmp_path / "bench")]
    argv += ["--out", str(tmp_path / "out"), "--image-digest", "latest"]
    done = subprocess.run(argv, env=env, capture_output=True, text=True, check=False)
    assert done.returncode == 2 and "--image-digest sha256:" in done.stderr
    assert not (tmp_path / "out").exists()


# --- the owner's runner script: checked through --dry-run, never by running Docker ------------

SH = ROOT / "scripts" / "clitoolbench_freeze.sh"


def run_sh(
    tmp_path: Path, *args: str, home: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """The runner with a fake `docker` first on PATH that logs and fails: a dry run must never
    reach it, and a broken dry run cannot reach a real Docker either."""
    fake = tmp_path / "fakebin"
    fake.mkdir(exist_ok=True)
    (fake / "docker").write_text(f'#!/bin/sh\necho "$@" >> {tmp_path}/docker-called\nexit 99\n')
    (fake / "docker").chmod(0o755)
    env = {"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(home or tmp_path / "home")}
    return subprocess.run(
        ["/bin/sh", str(SH), *args], env=env, capture_output=True, text=True, check=False
    )


def test_the_runner_hardens_both_containers_and_cuts_the_network_for_the_run_phase(
    tmp_path: Path,
) -> None:
    bench = tmp_path / "bench"
    bench.mkdir()
    done = run_sh(tmp_path, "--dry-run", "--image-digest", DIGEST, str(bench), str(tmp_path / "o"))
    assert done.returncode == 0, done.stderr
    assert not (tmp_path / "docker-called").exists() and not (tmp_path / "o").exists()
    lines = done.stdout.splitlines()
    build = next(line for line in lines if line.startswith("docker build"))
    assert f"--build-arg BASE_DIGEST={DIGEST}" in build
    install = next(line for line in lines if "--phase install" in line).split()
    run = next(line for line in lines if "--phase run" in line).split()
    uid_gid = f"{os.getuid()}:{os.getgid()}"
    for argv in (install, run):
        flags = " ".join(argv)
        for flag in (
            f"--user {uid_gid}",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
            "--pids-limit 512",
            "--memory 4g",
            "--cpus 2",
            "--stop-timeout 10",
            f"-v {bench.resolve()}:/bench:ro",
            f"--image-digest {DIGEST}",
            "--rm",
        ):
            assert flag in flags, flag
        assert "--chown" not in flags
        volume = next(a for a in argv if a.endswith(":/clitb-work"))
        assert volume.startswith("antstreet-clitb-work-")
    assert "--network none" in " ".join(run) and "--network" not in install
    assert not any(a.endswith(":/out") for a in install)
    assert f"{(tmp_path / 'o').resolve()}:/out" in " ".join(run)


@pytest.mark.parametrize(
    ("digest", "message"),
    [("", "digest of the base image"), ("sha256:abc", "digest of the base image")],
)
def test_the_runner_requires_the_pulled_image_digest(
    tmp_path: Path, digest: str, message: str
) -> None:
    (tmp_path / "bench").mkdir()
    args = ["--dry-run", *(["--image-digest", digest] if digest else [])]
    done = run_sh(tmp_path, *args, str(tmp_path / "bench"), str(tmp_path / "o"))
    assert done.returncode == 2 and message in done.stderr
    assert "docker inspect" in done.stderr


def test_the_runner_refuses_an_unsafe_or_used_out_dir(tmp_path: Path) -> None:
    bench = tmp_path / "bench"
    bench.mkdir()
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    used = tmp_path / "used"
    used.mkdir()
    (used / "x").write_text("x")
    for out, message in (
        (used, "is not empty"),
        (ROOT / "frozen-here", "inside the repository"),
        (home / ".ssh" / "frozen", "dot folder"),
    ):
        done = run_sh(
            tmp_path, "--dry-run", "--image-digest", DIGEST, str(bench), str(out), home=home
        )
        assert done.returncode == 2 and message in done.stderr, (out, done.stderr)
        assert "docker" not in done.stdout
    assert not (ROOT / "frozen-here").exists() and not (tmp_path / "docker-called").exists()


def test_the_image_is_pinned_by_digest_and_runs_unprivileged() -> None:
    text = (ROOT / "scripts" / "clitoolbench_freeze.Dockerfile").read_text()
    assert "FROM python:3.12-bookworm@${BASE_DIGEST}" in text
    assert "USER 10001:10001" in text
    assert "chmod 1777 /test_data /clitb-work /clitb-work/repo" in text
    assert "ln -s /clitb-work/repo /repo" in text


@pytest.mark.skipif(shutil.which("git") is None, reason="the fake oracle is a local git repo")
def test_the_image_digest_reaches_the_index_and_the_manifest(tmp_path: Path) -> None:
    fake_checkout(tmp_path)
    out = run_freeze(tmp_path, "out", "--task", "acme/greet", "--cases-per-task", "3")
    assert json.loads((out / "index.json").read_text())["image_digest"] == DIGEST
    manifest = imported.convert_clitoolbench_all(out, tmp_path / "pool")
    assert manifest["image_digest"] == DIGEST


# --- every refusal path of the converter, named by what it refuses ---------------------------


def header(**change: Any) -> dict[str, Any]:
    oracle = {
        "url": "https://github.com/acme/greet.git",
        "commit": COMMIT,
        "licence": "MIT",
        "python": "3.12.7",
        "deps": [],
        "programs": ["greet"],
    }
    oracle.update(change.pop("oracle", {}))
    return {"oracle": oracle, **change}


@pytest.mark.parametrize(
    ("top", "message"),
    [
        (header(test_data_dir="relative/dir"), "test_data_dir must be an absolute path"),
        (header(ignore_dirs=["../up"]), "ignore_dirs must be a list of folder names"),
        (header(flags="not-a-list"), "flags must be a list"),
        (header(oracle={"url": ""}), "oracle.url must be a short string"),
        (header(oracle={"commit": "xyz"}), "oracle.commit must be a 40-hex git sha"),
        (header(oracle={"deps": "click"}), "oracle.deps must be a list of strings"),
        (header(oracle={"programs": ["a-b", "a.b"]}), "map to the same module 'a_b'"),
    ],
)
def test_each_bad_header_field_is_refused_by_name(
    tmp_path: Path, top: dict[str, Any], message: str
) -> None:
    with pytest.raises(ConvertError, match=re.escape(message)):
        convert_clitoolbench(frozen(tmp_path, **top), tmp_path / "tasks")
    assert not (tmp_path / "tasks").exists()


def without(key: str) -> list[dict[str, Any]]:
    c = json.loads(json.dumps(CASES[0]))
    if key == "expected.stdout":
        del c["expected"]["stdout"]
    else:
        del c[key]
    return [c]


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        (without("argv"), "keys must be"),
        (without("expected.stdout"), "expected must have exit_code, stdout and fs_delta"),
        (bad(argv="greet World"), "argv must be null or a list of strings"),
        (bad(env=["GREETING=Hi"]), "env must be an object"),
        (bad(fixtures=["names.txt"]), "fixtures must be an object"),
        (bad(fixtures={"a": {"base64": "%%%"}}), "is not valid base64"),
        (bad(fixtures={"a": 5}), "must be text or"),
        (bad(fs_delta=["out.txt"]), "fs_delta must be an object"),
        (
            bad(fs_delta={"o": {"type": "ADD", "sha256": sha("x"), "content": 5}}),
            "not base64 up to 1 MiB",
        ),
    ],
)
def test_each_bad_case_field_is_refused_by_name(
    tmp_path: Path, cases: list[dict[str, Any]], message: str
) -> None:
    with pytest.raises(ConvertError, match=re.escape(message)):
        convert_clitoolbench(frozen(tmp_path, cases), tmp_path / "tasks")


def test_fixtures_over_the_per_case_total_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(imported, "MAX_CASE_FIXTURE_BYTES", 10)
    cases = bad(fixtures={"a": "x" * 6, "b": "y" * 6})
    with pytest.raises(ConvertError, match="fixtures total more than 10 bytes"):
        convert_clitoolbench(frozen(tmp_path, cases), tmp_path / "tasks")


def test_a_program_name_is_made_a_module_name_python_can_run() -> None:
    assert imported._modules(["files-to-prompt", "1tool", "a.b"]) == {
        "files-to-prompt": "files_to_prompt",
        "1tool": "_1tool",
        "a.b": "a_b",
    }


def test_an_empty_spec_a_second_conversion_and_a_missing_or_linked_folder_are_refused(
    tmp_path: Path,
) -> None:
    src = frozen(tmp_path / "a")
    convert_clitoolbench(src, tmp_path / "t")
    with pytest.raises(ConvertError, match="already exists"):
        convert_clitoolbench(src, tmp_path / "t")
    (src / "spec.md").write_text("  \n")
    with pytest.raises(ConvertError, match="spec.md is empty"):
        convert_clitoolbench(src, tmp_path / "t2")
    with pytest.raises(ConvertError, match="cannot read"):
        convert_clitoolbench(tmp_path / "nowhere", tmp_path / "t3")
    (tmp_path / "linked").symlink_to(src, target_is_directory=True)
    with pytest.raises(ConvertError, match="is a symlink or not a folder"):
        convert_clitoolbench(tmp_path / "linked", tmp_path / "t3")


@pytest.mark.parametrize(
    ("text", "reason"),
    [("{not json", "(skipped.json is not valid JSON)"), ('["no", "reason"]', "(no reason given)")],
)
def test_a_skipped_json_without_a_usable_reason_still_refuses(
    tmp_path: Path, text: str, reason: str
) -> None:
    src = frozen(tmp_path)
    (src / "skipped.json").write_text(text)
    with pytest.raises(ConvertError, match=re.escape(reason)):
        convert_clitoolbench(src, tmp_path / "t")


# --- the playback reads a tool's arguments only where the shell line makes them plain --------


@pytest.mark.parametrize(
    ("command", "argv"),
    [
        ("greet World --shout", ["World", "--shout"]),
        ("printf 'Bo\\n' | greet --stdin", ["--stdin"]),
        ("greet a && echo done", ["a"]),
        ("greet a > {TEST_DATA}/out.txt", ["a"]),
        ("greet 'unbalanced", None),  # the shell itself would refuse it
        ("greet a; greet b", None),  # runs twice: which run printed what is unknown
        ("echo hi", None),  # never runs the tool
        ('greet "$(cat {TMP}/n.txt)"', None),  # the shell computes the argument
        ("X=$HOME greet a", None),  # an expansion before the tool
    ],
)
def test_the_playback_identifies_only_plainly_readable_runs(
    command: str, argv: list[str] | None
) -> None:
    assert imported._replay_argv(command, "greet") == argv


def test_a_replay_that_did_not_run_sandboxed_is_a_problem_before_anything_else() -> None:
    report = imported.ReplayReport(1.0, ("c0001",), (), ("c0001",), sandboxed=False)
    assert report.problem == "the replay did not run sandboxed"


# --- --all refuses a bad freeze output as a whole ---------------------------------------------


def test_convert_all_refuses_a_freeze_output_it_cannot_trust(tmp_path: Path, capsys: Any) -> None:
    (tmp_path / "file").write_text("x")
    for target, message in (
        (tmp_path / "file", "is a symlink or not a folder"),
        (tmp_path / "missing", "cannot read"),
    ):
        with pytest.raises(ConvertError, match=message):
            imported.convert_clitoolbench_all(target, tmp_path / "pool")
    out = freeze_output(tmp_path)
    index = json.loads((out / "index.json").read_text())
    for broken, message in (
        ({**index, "format": "other/1"}, "format must be"),
        ({**index, "skipped": ["acme/gone"]}, "skipped must be an object"),
    ):
        (out / "index.json").write_text(json.dumps(broken))
        with pytest.raises(ConvertError, match=message):
            imported.convert_clitoolbench_all(out, tmp_path / "pool")
    assert main(["nl2repo", str(out), str(tmp_path / "pool"), "--all"]) == 2
    assert "--all is for clitoolbench" in capsys.readouterr().err
    assert not (tmp_path / "pool").exists()


def test_convert_all_never_overwrites_a_task_already_in_the_pool(tmp_path: Path) -> None:
    out = freeze_output(tmp_path)
    pool = tmp_path / "pool"
    imported.convert_clitoolbench_all(out, pool)
    (pool / "clitoolbench-manifest.json").unlink()  # a second run into the same pool
    manifest = imported.convert_clitoolbench_all(out, pool)
    assert manifest["kept"] == []
    reasons = {r["task"]: r["reason"] for r in manifest["dropped"]}
    assert "clitb-greet already exists" in reasons["acme/greet"]
    assert not list(pool.glob("staging-*"))
