"""Turn a task downloaded from an external benchmark into a bench task folder (see `tasks.py`).

    python -m antstreet.bench.imported nl2repo <task-dir> <dest-root>
    python -m antstreet.bench.imported clitoolbench <task-dir> <dest-root> [--stdout-match fm]

writes `<dest-root>/<task-id>/` with `idea.md` (the spec), `hidden/` (its pytest tree), `meta.json`
and, where the tests import a module the gate lacks, `support/`. The source stays where it is and
nothing is fetched: external task data is never committed here, so `<dest-root>` belongs outside
the repository (the benchmark takes it with `--tasks`).

nl2repo task folder: `start.md`, `tests/`, `test_commands.json` (the last command is the pytest
run; its last word is the test path inside the product), `test_case_count.txt`.

clitoolbench task folder: what `scripts/clitoolbench_freeze.py` wrote for one task, `cases.json`
(the oracle's recorded behaviour, see `_load_frozen` for the schema) and `spec.md`. The converter
re-checks every field: the file came out of a container that ran third-party code.
"""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import inspect
import json
import re
import shlex
import shutil
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from antstreet.bench.tasks import (
    IMPORTED_SOURCES,
    SHIMS,
    BenchTask,
    TaskError,
    load_task,
    run_imported,
    validate_task,
)
from antstreet.gate import TREE_TIMEOUT_S

_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc")


class ConvertError(Exception):
    """The source folder is not a task this converter understands. Says what is missing."""


def convert_nl2repo(src: Path, dest_root: Path, task_id: str | None = None) -> Path:
    task_id = task_id or src.name
    dest = dest_root / task_id
    if dest.exists():
        raise ConvertError(f"{dest} already exists; remove it to convert again")
    spec = _read(src / "start.md")
    count = _count(src / "test_case_count.txt")
    test_path = _test_path(src / "test_commands.json")
    tests = src / test_path
    if not tests.is_dir():
        raise ConvertError(f"{tests} is not a folder; test_commands.json names {test_path!r}")
    dest.mkdir(parents=True)
    (dest / "idea.md").write_text(spec.strip() + "\n", encoding="utf-8")
    shutil.copytree(tests, dest / "hidden", ignore=_IGNORE)
    for name in sorted(_imported_names(dest / "hidden") & SHIMS.keys()):
        (dest / "support").mkdir(exist_ok=True)
        (dest / "support" / f"{name}.py").write_text(SHIMS[name], encoding="utf-8")
    meta = {
        "id": task_id,
        "title": f"{task_id} (NL2Repo-Bench)",
        "difficulty": "hard",
        "imported": {"source": "nl2repo", "test_path": test_path, "test_count": count},
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return dest


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConvertError(f"cannot read {path}: {exc}") from exc


def _count(path: Path) -> int:
    try:
        return int(_read(path).strip())
    except ValueError as exc:
        raise ConvertError(f"{path} must hold one whole number") from exc


def _test_path(path: Path) -> str:
    try:
        commands = json.loads(_read(path))
    except ValueError as exc:
        raise ConvertError(f"{path} is not valid JSON") from exc
    pytest_runs = [c for c in commands if isinstance(c, str) and c.split()[:1] == ["pytest"]]
    if not isinstance(commands, list) or len(pytest_runs) != 1:
        raise ConvertError(f"{path} must list exactly one `pytest ...` command")
    return pytest_runs[0].split()[-1]


def _imported_names(tree: Path) -> set[str]:
    names: set[str] = set()
    for source in tree.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


# --- CLI-Tool-Bench, frozen -------------------------------------------------------------------

FROZEN_FORMAT = "antstreet-clitoolbench-frozen/1"
FROZEN_MAX_BYTES = 16 * 1024 * 1024
SPEC_MAX_BYTES = 1024 * 1024
MAX_CASES = 2000
MAX_STDOUT_CHARS = 64 * 1024
MAX_COMMAND_CHARS = 4096
MAX_FIXTURES = 200
MAX_FIXTURE_BYTES = 1024 * 1024
MAX_CASE_FIXTURE_BYTES = 8 * 1024 * 1024
CASE_TIMEOUT_S = 10  # per shell run inside one case (prep, then the command)
STDOUT_MATCHES = ("em", "fm")
FM_MIN_PERCENT = 80  # pre-registered: Levenshtein ratio >= 0.8
FM_MAX_CHARS = 3000  # the LCS table is quadratic; above this FM is exact match (stricter)
# The same text is in scripts/clitoolbench_freeze.py (a test holds them equal): the oracle's
# stdout and the product's lose their colour codes the same way.
ANSI_PATTERN = r"\x1b\[[0-?]*[ -/]*[@-~]"
TEST_DATA, TMP = "{TEST_DATA}", "{TMP}"
# Set by the replay; a case may not override them (PYTHONPATH would swap the product, PATH the
# launcher).
_HARNESS_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONIOENCODING",
        "LANG",
        "LC_ALL",
        "CLITB_PYTHON",
    }
)
_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_TASK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
_CASE_ID = re.compile(r"c[0-9]{4,6}\Z")
_PROGRAM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_DIR_NAME = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")


def fm_match(actual: str, expected: str) -> bool:
    """Fuzzy match: Levenshtein (indel) ratio 2*LCS/(len(a)+len(b)) of at least FM_MIN_PERCENT.

    Integer arithmetic, so 0.8 exactly passes. Above FM_MAX_CHARS only an exact match passes.
    """
    if actual == expected:
        return True
    total = len(actual) + len(expected)
    if max(len(actual), len(expected)) > FM_MAX_CHARS:
        return False
    if 100 * 2 * min(len(actual), len(expected)) < FM_MIN_PERCENT * total:
        return False  # even the whole shorter string in common cannot reach the ratio
    row = [0] * (len(expected) + 1)
    for a in actual:
        diagonal = 0
        for j, b in enumerate(expected, 1):
            above = row[j]
            row[j] = diagonal + 1 if a == b else max(above, row[j - 1])
            diagonal = above
    return 100 * 2 * row[-1] >= FM_MIN_PERCENT * total


def convert_clitoolbench(
    src: Path, dest_root: Path, task_id: str | None = None, *, stdout_match: str = "em"
) -> Path:
    """Write a frozen CLI-Tool-Bench task as an imported task: one hidden test per frozen case."""
    if stdout_match not in STDOUT_MATCHES:
        raise ConvertError(f"stdout_match must be one of {STDOUT_MATCHES}, not {stdout_match!r}")
    if (src / "skipped.json").is_file():
        raise ConvertError(f"{src} was skipped by the freeze: {_read(src / 'skipped.json')}")
    data = _load_frozen(src / "cases.json")
    spec = _read_bounded(src / "spec.md", SPEC_MAX_BYTES).strip()
    if not spec:
        raise ConvertError(f"{src / 'spec.md'} is empty")
    repo = data["task"].split("/")[1].lower().replace("_", "-").replace(".", "-")
    task_id = task_id or f"clitb-{repo}"[:41].rstrip("-")
    dest = dest_root / task_id
    if dest.exists():
        raise ConvertError(f"{dest} already exists; remove it to convert again")
    programs = _modules(data["oracle"]["programs"])
    cases = data["cases"]
    flags = list(data["flags"])
    if data["oracle"]["deps"]:
        flags.append("oracle_needs_third_party")
    (dest / "hidden").mkdir(parents=True)
    (dest / "idea.md").write_text(_addendum(spec, data["task"], programs, stdout_match))
    replay = {
        "programs": programs,
        "stdout_match": stdout_match,
        "case_timeout_s": CASE_TIMEOUT_S,
        "test_data_dir": data["test_data_dir"],
        "ignore_dirs": data["ignore_dirs"],
        "cases": [_without_content(c) for c in cases],
    }
    (dest / "hidden" / "cases.json").write_text(json.dumps(replay, indent=1) + "\n")
    (dest / "hidden" / "__init__.py").write_text("")
    ids = [c["id"] for c in cases]
    (dest / "hidden" / "test_cases.py").write_text(_replay_source(ids), encoding="utf-8")
    provenance = {
        "source": "clitoolbench",
        "task": data["task"],
        "seed": data["seed"],
        "cases_per_task": data["cases_per_task"],
        "oracle": data["oracle"],
        "stdout_match": stdout_match,
        "programs": programs,
        "flags": flags,
        "dropped": len(data["dropped"]),
    }
    (dest / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    meta = {
        "id": task_id,
        "title": f"{data['task']} (CLI-Tool-Bench, frozen)",
        "difficulty": "hard",
        "imported": {
            "source": "clitoolbench",
            "test_path": "tests",
            "test_count": len(cases),
            "test_timeout_s": 2 * CASE_TIMEOUT_S + 5,
        },
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    return dest


def _read_bounded(path: Path, limit: int) -> str:
    if path.is_symlink():
        raise ConvertError(f"{path} is a symlink; the frozen task must be plain files")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ConvertError(f"cannot read {path}: {exc}") from exc
    if size > limit:
        raise ConvertError(f"{path} is larger than {limit} bytes")
    return _read(path)


def _load_frozen(path: Path) -> dict[str, Any]:
    """cases.json, every field checked. Its shape:

    {"format": FROZEN_FORMAT, "task": "owner/repo", "seed": int, "cases_per_task": N,
     "test_data_dir": "/test_data", "ignore_dirs": [name], "flags": [str], "dropped": [...],
     "oracle": {"url", "commit" (40 hex), "licence", "python", "deps": [str], "programs": [name]},
     "cases": [{"id": "c0001", "category", "command" (sh -c), "argv": [str] | null, "stdin",
                "env": {KEY: value}, "prep_script", "fixtures": {rel path: text | {"base64": s}},
                "expected": {"exit_code": 0-255, "stdout", "fs_delta": {rel path:
                             {"type": "ADD" | "MOD" | "DEL", "sha256": hex | null,
                              "content": base64 (ADD/MOD, optional; must hash to sha256)}}}}]}

    Exactly N cases (the freeze's fixed count).

    Paths in commands, stdout and file contents use "{TEST_DATA}" and "{TMP}" for the folders.
    """
    try:
        data = json.loads(_read_bounded(path, FROZEN_MAX_BYTES))
    except ValueError as exc:
        raise ConvertError(f"{path} is not valid JSON") from exc
    if not isinstance(data, dict) or data.get("format") != FROZEN_FORMAT:
        raise ConvertError(f"{path}: format must be {FROZEN_FORMAT!r}")
    if not isinstance(data.get("task"), str) or not _TASK.match(data["task"]):
        raise ConvertError(f"{path}: task must be 'owner/repo'")
    for key in ("seed", "cases_per_task"):
        if not _is_int(data.get(key)) or data[key] < 0:
            raise ConvertError(f"{path}: {key} must be a whole number")
    data.setdefault("test_data_dir", "/test_data")
    data.setdefault("ignore_dirs", [])
    data.setdefault("flags", [])
    data.setdefault("dropped", [])
    td = data["test_data_dir"]
    if not isinstance(td, str) or not td.startswith("/") or len(td) > 255 or "\x00" in td:
        raise ConvertError(f"{path}: test_data_dir must be an absolute path")
    if not _str_list(data["ignore_dirs"], 100) or not all(
        _DIR_NAME.match(d) for d in data["ignore_dirs"]
    ):
        raise ConvertError(f"{path}: ignore_dirs must be a list of folder names")
    if not _str_list(data["flags"], 50) or not isinstance(data["dropped"], list):
        raise ConvertError(f"{path}: flags must be a list of strings and dropped a list")
    _check_oracle(path, data.get("oracle"))
    cases = data.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ConvertError(f"{path}: cases must be a list of 1 to {MAX_CASES} cases")
    seen: set[str] = set()
    for i, case in enumerate(cases):
        name = case.get("id") if isinstance(case, dict) else None
        if not isinstance(name, str) or not _CASE_ID.match(name):
            raise ConvertError(f"{path}: case {i} has a bad id; ids are 'c' and 4 to 6 digits")
        if name in seen:
            raise ConvertError(f"{path}: duplicate case id {name}")
        seen.add(name)
        problem = _case_problem(case)
        if problem:
            raise ConvertError(f"{path}: case {name}: {problem}")
    if len(cases) != data["cases_per_task"]:
        raise ConvertError(
            f"{path}: {len(cases)} cases, but cases_per_task says {data['cases_per_task']}"
        )
    return data


def _check_oracle(path: Path, oracle: object) -> None:
    keys = {"url", "commit", "licence", "python", "deps", "programs"}
    if not isinstance(oracle, dict) or set(oracle) != keys:
        raise ConvertError(f"{path}: oracle must have exactly {sorted(keys)}")
    for key in ("url", "licence", "python"):
        value = oracle[key]
        if not isinstance(value, str) or not value or len(value) > 500 or "\x00" in value:
            raise ConvertError(f"{path}: oracle.{key} must be a short string")
    if not isinstance(oracle["commit"], str) or not _COMMIT.match(oracle["commit"]):
        raise ConvertError(f"{path}: oracle.commit must be a 40-hex git sha")
    if not _str_list(oracle["deps"], 500):
        raise ConvertError(f"{path}: oracle.deps must be a list of strings")
    programs = oracle["programs"]
    if not _str_list(programs, 10) or not programs or not all(_PROGRAM.match(p) for p in programs):
        raise ConvertError(f"{path}: oracle.programs must be 1 to 10 plain program names")


def _case_problem(case: dict[str, Any]) -> str | None:
    keys = {"id", "category", "command", "argv", "stdin", "env", "prep_script", "fixtures"}
    if set(case) != keys | {"expected"}:
        return f"keys must be {sorted(keys | {'expected'})}"
    for key, limit, empty_ok in (
        ("command", MAX_COMMAND_CHARS, False),
        ("prep_script", MAX_COMMAND_CHARS, True),
        ("category", 200, True),
        ("stdin", MAX_STDOUT_CHARS, True),
    ):
        value = case[key]
        if not isinstance(value, str) or len(value) > limit or "\x00" in value:
            return f"{key} must be a string of at most {limit} characters, no NUL"
        if not value and not empty_ok:
            return f"{key} is empty"
    argv = case["argv"]
    if argv is not None and not _str_list(argv, 200):
        return "argv must be null or a list of strings"
    env = case["env"]
    if not isinstance(env, dict) or len(env) > 50:
        return "env must be an object of at most 50 entries"
    for key, value in env.items():
        if not _ENV_KEY.match(key) or key in _HARNESS_ENV or not isinstance(value, str):
            return f"env key {key!r} is not allowed (the harness sets {sorted(_HARNESS_ENV)})"
    return _fixtures_problem(case["fixtures"]) or _expected_problem(case["expected"])


def _fixtures_problem(fixtures: object) -> str | None:
    if not isinstance(fixtures, dict) or len(fixtures) > MAX_FIXTURES:
        return f"fixtures must be an object of at most {MAX_FIXTURES} files"
    total = 0
    for rel, content in fixtures.items():
        if not _safe_rel(rel):
            return f"fixture path {rel!r} must be relative, inside the test folder"
        if isinstance(content, str):
            size = len(content.encode("utf-8", "surrogatepass"))
        elif isinstance(content, dict) and set(content) == {"base64"}:
            try:
                size = len(base64.b64decode(content["base64"], validate=True))
            except (binascii.Error, TypeError, ValueError):
                return f"fixture {rel!r} is not valid base64"
        else:
            return f"fixture {rel!r} must be text or {{'base64': ...}}"
        if size > MAX_FIXTURE_BYTES:
            return f"fixture {rel!r} is larger than {MAX_FIXTURE_BYTES} bytes"
        total += size
    if total > MAX_CASE_FIXTURE_BYTES:
        return f"fixtures total more than {MAX_CASE_FIXTURE_BYTES} bytes"
    return None


def _expected_problem(expected: object) -> str | None:
    if not isinstance(expected, dict) or set(expected) != {"exit_code", "stdout", "fs_delta"}:
        return "expected must have exit_code, stdout and fs_delta"
    if not _is_int(expected["exit_code"]) or not 0 <= expected["exit_code"] <= 255:
        return "expected exit_code must be a whole number 0-255"
    stdout = expected["stdout"]
    if not isinstance(stdout, str) or len(stdout) > MAX_STDOUT_CHARS:
        return f"expected stdout must be a string of at most {MAX_STDOUT_CHARS} characters"
    delta = expected["fs_delta"]
    if not isinstance(delta, dict) or len(delta) > MAX_FIXTURES:
        return f"expected fs_delta must be an object of at most {MAX_FIXTURES} files"
    for rel, change in delta.items():
        ok = isinstance(change, dict) and _safe_rel(rel)
        if ok and change.get("type") == "DEL":
            ok = set(change) == {"type", "sha256"} and change["sha256"] is None
        elif ok:
            digest = change.get("sha256")
            ok = change.get("type") in ("ADD", "MOD") and isinstance(digest, str)
            ok = ok and bool(_SHA256.match(digest)) and set(change) <= {"type", "sha256", "content"}
            if ok and "content" in change:
                content = _decode(change["content"])
                if content is None or len(content) > MAX_FIXTURE_BYTES:
                    return f"fs_delta entry {rel!r} has content that is not base64 up to 1 MiB"
                if hashlib.sha256(content).hexdigest() != digest:
                    return f"fs_delta entry {rel!r}: content does not hash to its sha256"
        if not ok:
            return f"fs_delta entry {rel!r} must be ADD/MOD with a sha256, or DEL with null"
    return None


def _decode(value: object) -> bytes | None:
    if not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None


def _without_content(case: dict[str, Any]) -> dict[str, Any]:
    delta = {
        rel: {"type": change["type"], "sha256": change["sha256"]}
        for rel, change in case["expected"]["fs_delta"].items()
    }
    return {**case, "expected": {**case["expected"], "fs_delta": delta}}


def _safe_rel(rel: object) -> bool:
    if not isinstance(rel, str) or not 0 < len(rel) <= 255 or "\x00" in rel or "\\" in rel:
        return False
    parts = rel.split("/")
    return all(p not in ("", ".", "..") for p in parts)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _str_list(value: object, limit: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= limit
        and all(isinstance(v, str) and len(v) <= 500 for v in value)
    )


def _modules(programs: list[str]) -> dict[str, str]:
    """Program name -> the module the product provides for it (`python -m <module>`)."""
    found: dict[str, str] = {}
    for program in programs:
        module = re.sub(r"[^A-Za-z0-9_]", "_", program)
        if module[0].isdigit():
            module = f"_{module}"
        if module in found.values():
            raise ConvertError(f"programs {programs} map to the same module {module!r}")
        found[program] = module
    return found


def _addendum(spec: str, task: str, programs: dict[str, str], stdout_match: str) -> str:
    runs = "\n".join(
        f"  - `{p} ARGS` runs `python -m {m} ARGS`: provide `{m}/__main__.py` (a package) or "
        f"`{m}.py` at the product root."
        for p, m in programs.items()
    )
    match = (
        "must equal the original tool's exactly"
        if stdout_match == "em"
        else "must be close to the original tool's (Levenshtein ratio at least 0.8)"
    )
    return f"""{spec}

---

## How this product is run and graded (harness addendum; every arm sees the same text)

This task is {task} from CLI-Tool-Bench. Where the text above says to make a pip-installable
package, a `repo_to_be_tested` folder or a console-script entry point, do this instead:

- Python 3.12, standard library only. No third-party package is installed when it is graded and
  nothing is pip-installed.
- The product folder's root is on `PYTHONPATH`, and each command is a shell line run with
  `/bin/sh -c` in which:
{runs}
- Each run starts in a fresh working folder that holds its input files, with no network and a
  fresh `HOME`. Absolute paths in the text above are only examples; the folders are temporary.
- Compared with the original tool, in this order: the exit code; the files created, changed or
  deleted under the working folder (content too); then stdout, which {match} after ANSI colour
  codes are removed. stderr is not compared.
"""


def _replay_source(ids: list[str]) -> str:
    return (
        _REPLAY.replace("@ANSI@", repr(ANSI_PATTERN))
        .replace("@FM_MIN_PERCENT@", str(FM_MIN_PERCENT))
        .replace("@FM_MAX_CHARS@", str(FM_MAX_CHARS))
        .replace("@FM@", inspect.getsource(fm_match).strip())
        .replace("@IDS@", repr(ids))
    )


# The generated hidden test: stdlib and pytest only. The case data sits next to it in cases.json.
_REPLAY = '''"""Replays frozen CLI-Tool-Bench cases (cases.json) against the product.

Generated by antstreet.bench.imported; do not edit. Per case: exit code, then the filesystem delta
under the working folder, then stdout.
"""

import base64
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PRODUCT = HERE.parent
DATA = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in DATA["cases"]}
IGNORED = frozenset(DATA["ignore_dirs"])
ANSI = re.compile(@ANSI@)
FM_MIN_PERCENT = @FM_MIN_PERCENT@
FM_MAX_CHARS = @FM_MAX_CHARS@
TEST_DATA, TMP = "{TEST_DATA}", "{TMP}"


@FM@


def _provided(module):
    return (PRODUCT / module / "__main__.py").is_file() or (PRODUCT / f"{module}.py").is_file()


def _launchers(bin_dir):
    bin_dir.mkdir()
    scripts = {"python": "", "python3": ""}
    scripts.update({name: f"-m {module} " for name, module in DATA["programs"].items()})
    for name, args in scripts.items():
        path = bin_dir / name
        path.write_text(f'#!/bin/sh\\nexec "$CLITB_PYTHON" {args}"$@"\\n')
        path.chmod(0o755)


def _normalise(data, real):
    for path, mark in real:
        data = data.replace(path.encode(), mark.encode())
    return data


def _state(root, real):
    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED)
        for name in filenames:
            path = Path(dirpath, name)
            if path.is_file() and not path.is_symlink():
                digest = hashlib.sha256(_normalise(path.read_bytes(), real)).hexdigest()
                found[path.relative_to(root).as_posix()] = digest
    return found


def _delta(before, after):
    delta = {}
    for rel in sorted(before.keys() | after.keys()):
        if rel not in after:
            delta[rel] = {"type": "DEL", "sha256": None}
        elif rel not in before:
            delta[rel] = {"type": "ADD", "sha256": after[rel]}
        elif before[rel] != after[rel]:
            delta[rel] = {"type": "MOD", "sha256": after[rel]}
    return delta


def _sh(script, cwd, env, stdin):
    proc = subprocess.Popen(
        ["/bin/sh", "-c", script],
        cwd=cwd,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(stdin, timeout=DATA["case_timeout_s"])
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        pytest.fail(f"the command took more than {DATA['case_timeout_s']}s")
    # A shell killed by a signal: report it the way sh would, 128 + the signal.
    code = proc.returncode
    return (code if code >= 0 else 128 - code), out, err


@pytest.mark.parametrize("case_id", @IDS@)
def test_case(case_id):
    case, expected = CASES[case_id], CASES[case_id]["expected"]
    missing = sorted(m for m in set(DATA["programs"].values()) if not _provided(m))
    assert not missing, f"the product has no module {missing} to run with python -m"
    with tempfile.TemporaryDirectory(prefix="clitb_") as raw:
        root = Path(raw).resolve()
        td, tmp, home = root / "test_data", root / "tmp", root / "home"
        for folder in (td, tmp, home):
            folder.mkdir()
        _launchers(root / "bin")
        real = [(str(td), TEST_DATA), (str(tmp), TMP), (DATA["test_data_dir"], TEST_DATA)]
        real.append(("/tmp", TMP))

        def place(text):
            return text.replace(TEST_DATA, str(td)).replace(TMP, str(tmp))

        env = {key: place(value) for key, value in case["env"].items()}
        env.update(
            PATH=os.pathsep.join([str(root / "bin"), "/usr/bin", "/bin"]),
            HOME=str(home),
            TMPDIR=str(tmp),
            LANG="C.UTF-8",
            LC_ALL="C.UTF-8",
            PYTHONPATH=str(PRODUCT),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONIOENCODING="utf-8",
            CLITB_PYTHON=sys.executable,
        )
        for rel, content in case["fixtures"].items():
            path = td / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, dict):
                path.write_bytes(base64.b64decode(content["base64"]))
            else:
                path.write_bytes(content.encode("utf-8", "surrogatepass"))
        if case["prep_script"]:
            _sh(place(case["prep_script"]), td, env, b"")
        before = _state(td, real)
        code, out, err = _sh(place(case["command"]), td, env, place(case["stdin"]).encode())
        delta = _delta(before, _state(td, real))
    assert code == expected["exit_code"], f"exit code {code}; stderr ends {err[-300:]!r}"
    assert delta == expected["fs_delta"], "files created, changed or deleted differ"
    stdout = ANSI.sub("", _normalise(out, real).decode("utf-8", "replace"))
    if DATA["stdout_match"] == "fm":
        assert fm_match(stdout, expected["stdout"]), "stdout is below the fuzzy-match ratio"
    else:
        assert stdout == expected["stdout"]
'''


# --- replay validation: the recorded outputs, played back through the real gate ---------------

REPLAY_MAX_S = TREE_TIMEOUT_S / 2  # a perfect product must finish in half the gate's suite cap
MANIFEST = "clitoolbench-manifest.json"
MANIFEST_FORMAT = "antstreet-clitoolbench-manifest/1"
_OPERATOR = re.compile(r"[();<>|&]+\Z")
_EXPANSION = re.compile(r"[$`*?\[~]")


@dataclass(frozen=True, slots=True)
class ReplayReport:
    seconds: float  # wall clock of grading the replay product, through the sandboxed gate
    verified: tuple[str, ...]  # cases the replay product can identify; each must pass
    unverified: tuple[str, ...]  # cases it cannot (shell expansion, 0 or 2+ runs of the tool)
    failed: tuple[str, ...]  # verified cases that did not pass: no product could
    sandboxed: bool  # the replay ran inside the OS sandbox (run_imported refuses otherwise)

    @property
    def problem(self) -> str | None:
        if not self.sandboxed:
            return "the replay did not run sandboxed"
        if self.failed:
            return f"the recorded outputs replayed fail {list(self.failed)}: no product can pass"
        if self.seconds > REPLAY_MAX_S:
            return f"the replay took {self.seconds:.0f}s, over {REPLAY_MAX_S:.0f}s"
        return None


def _replay_argv(command: str, program: str) -> list[str] | None:
    """The arguments the program gets in this shell line, when that is plain to read: it runs
    once, and nothing up to the next shell operator is expanded by the shell."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None
    if tokens.count(program) != 1 or _EXPANSION.search(command.split(program, 1)[0]):
        return None
    args: list[str] = []
    for token in tokens[tokens.index(program) + 1 :]:
        if _OPERATOR.match(token):
            break
        args.append(token)
    rest = command.split(program, 1)[1]
    end = min((rest.find(c) for c in "();<>|&" if c in rest), default=len(rest))
    if _EXPANSION.search(rest[:end]):
        return None
    return args


def _replay_entries(cases: list[dict[str, Any]], programs: dict[str, str]) -> list[dict[str, Any]]:
    entries = []
    for case in cases:
        hits = [(p, _replay_argv(case["command"], p)) for p in programs if p in case["command"]]
        delta = case["expected"]["fs_delta"]
        if (
            len(hits) != 1
            or hits[0][1] is None
            or any(c["type"] != "DEL" and "content" not in c for c in delta.values())
        ):
            continue
        fixtures = {}
        for rel, content in case["fixtures"].items():
            raw = (
                base64.b64decode(content["base64"])
                if isinstance(content, dict)
                else content.encode("utf-8", "surrogatepass")
            )
            fixtures[rel] = hashlib.sha256(raw).hexdigest()
        entries.append(
            {
                "id": case["id"],
                "program": hits[0][0],
                "argv": hits[0][1],
                "fixtures": fixtures,
                "exit_code": case["expected"]["exit_code"],
                "stdout": case["expected"]["stdout"],
                "delta": delta,
            }
        )
    return entries


def replay_check(task: BenchTask, src: Path) -> ReplayReport:
    """Grade a product that plays back the frozen outputs, through the real sandboxed gate.

    Run by `--all`. A case the playback cannot identify still runs (it counts for the time) but
    is not required to pass; every case it can identify must, or the frozen outputs are not
    reachable by any product. Seconds over REPLAY_MAX_S mean a correct product could time out.
    """
    data = _load_frozen(src / "cases.json")
    programs = _modules(data["oracle"]["programs"])
    entries = _replay_entries(data["cases"], programs)
    with tempfile.TemporaryDirectory(prefix="clitb_replay_") as raw:
        product = Path(raw)
        (product / "clitb_replay.json").write_text(json.dumps(entries))
        for program, module in programs.items():
            (product / module).mkdir()
            (product / module / "__init__.py").write_text("")
            (product / module / "__main__.py").write_text(
                _PLAYBACK.replace("@PROGRAM@", repr(program))
            )
        start = time.monotonic()
        run = run_imported(task, product)
        seconds = time.monotonic() - start
    hidden = {node: str(status) for node, status in run.tests.items()}
    verified = tuple(e["id"] for e in entries)
    failed = tuple(
        cid for cid in verified if hidden.get(f"tests/test_cases.py::test_case[{cid}]") != "passed"
    )
    unverified = tuple(c["id"] for c in data["cases"] if c["id"] not in verified)
    return ReplayReport(seconds, verified, unverified, failed, run.sandboxed)


# The replay product's entry point. Harness-owned: it knows the replay's folder layout (the
# working folder is "test_data" next to TMPDIR), which no real product is told.
_PLAYBACK = """import base64, hashlib, json, sys, tempfile
from pathlib import Path

PROGRAM = @PROGRAM@
ENTRIES = json.loads((Path(__file__).resolve().parent.parent / "clitb_replay.json").read_text())
TMP = tempfile.gettempdir()  # the replay's TMPDIR
TD = str(Path(TMP).parent / "test_data")


def norm(text):
    return text.replace(TD, "{TEST_DATA}").replace(TMP, "{TMP}")


def place(text):
    return text.replace("{TEST_DATA}", TD).replace("{TMP}", TMP)


def matches(entry):
    if entry["program"] != PROGRAM or entry["argv"] != [norm(a) for a in sys.argv[1:]]:
        return False
    for rel, digest in entry["fixtures"].items():
        path = Path(TD, rel)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            return False
    return True


hits = [e for e in ENTRIES if matches(e)]
if len(hits) != 1:
    sys.exit(0)
entry = hits[0]
for rel, change in entry["delta"].items():
    path = Path(TD, rel)
    if change["type"] == "DEL":
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = base64.b64decode(change["content"])
        path.write_bytes(place(content.decode("latin-1")).encode("latin-1"))
sys.stdout.write(place(entry["stdout"]))
sys.stdout.flush()
sys.exit(entry["exit_code"])
"""


def convert_clitoolbench_all(
    freeze_out: Path, dest_root: Path, *, stdout_match: str = "em"
) -> dict[str, Any]:
    """Convert, validate and replay-check every task of one freeze; write the manifest.

    Only tasks that pass all three land in `dest_root`; each one dropped (by the freeze, the
    converter, validation or the replay) is listed with its reason. The manifest sits in
    `dest_root`, so the pre-registration digest (task_set_digest) covers it.
    """
    index = json.loads(_read_bounded(freeze_out / "index.json", FROZEN_MAX_BYTES))
    if not isinstance(index, dict) or index.get("format") != FROZEN_FORMAT:
        raise ConvertError(f"{freeze_out / 'index.json'}: format must be {FROZEN_FORMAT!r}")
    if (dest_root / MANIFEST).exists():
        raise ConvertError(f"{dest_root / MANIFEST} already exists; use a fresh dest-root")
    dest_root.mkdir(parents=True, exist_ok=True)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, str]] = [
        {"task": str(task), "stage": "freeze", "reason": str(reason)}
        for task, reason in sorted(dict(index.get("skipped") or {}).items())
    ]
    for src in sorted(p for p in freeze_out.iterdir() if (p / "cases.json").is_file()):
        staging = Path(tempfile.mkdtemp(prefix="staging-", dir=dest_root))
        stage, task_name = "convert", src.name
        try:
            dest = convert_clitoolbench(src, staging, stdout_match=stdout_match)
            data = _load_frozen(src / "cases.json")
            task_name = data["task"]
            stage = "validate"
            task = load_task(dest)
            validate_task(task)
            stage = "replay"
            report = replay_check(task, src)
            if report.problem:
                raise ConvertError(report.problem)
            if (dest_root / dest.name).exists():
                raise ConvertError(f"{dest_root / dest.name} already exists")
            dest.rename(dest_root / dest.name)
            kept.append(
                {
                    "task": task_name,
                    "id": dest.name,
                    "cases": len(data["cases"]),
                    "oracle": {k: data["oracle"][k] for k in ("url", "commit", "licence")},
                    "python": data["oracle"]["python"],
                    "replay_s": round(report.seconds, 1),
                    "replay_unverified": list(report.unverified),
                }
            )
        except (ConvertError, TaskError) as exc:
            dropped.append({"task": task_name, "stage": stage, "reason": str(exc)})
        finally:
            shutil.rmtree(staging)  # made by this call; empty after a kept task's rename
    manifest = {
        "format": MANIFEST_FORMAT,
        "seed": index.get("seed"),
        "cases_per_task": index.get("cases_per_task"),
        "freeze_python": index.get("python"),
        "stdout_match": stdout_match,
        "replay_max_s": REPLAY_MAX_S,
        "kept": kept,
        "dropped": dropped,
    }
    (dest_root / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m antstreet.bench.imported", description=__doc__)
    parser.add_argument("source", choices=IMPORTED_SOURCES)
    parser.add_argument("task_dir", type=Path, help="the downloaded task folder")
    parser.add_argument("dest_root", type=Path, help="tasks folder to write into, outside the repo")
    parser.add_argument("--id", help="task id (default: the folder's name; clitb-<repo>)")
    parser.add_argument(
        "--stdout-match",
        choices=STDOUT_MATCHES,
        default="em",
        help="clitoolbench only: exact (em, pre-registered) or Levenshtein ratio >= 0.8 (fm)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="clitoolbench only: task_dir is a whole freeze output; convert, validate and "
        "replay-check every task and write the manifest into dest_root",
    )
    args = parser.parse_args(argv)
    if args.all:
        return _main_all(args.source, args.task_dir, args.dest_root, args.stdout_match)
    try:
        if args.source == "clitoolbench":
            dest = convert_clitoolbench(
                args.task_dir, args.dest_root, args.id, stdout_match=args.stdout_match
            )
            _warn_flags(dest)
        else:
            dest = convert_nl2repo(args.task_dir, args.dest_root, args.id)
        task = load_task(dest)
        print(f"wrote {dest}")
        validate_task(task)
    except (ConvertError, TaskError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"task {task.id} is valid")
    return 0


def _main_all(source: str, freeze_out: Path, dest_root: Path, stdout_match: str) -> int:
    if source != "clitoolbench":
        print("error: --all is for clitoolbench", file=sys.stderr)
        return 2
    try:
        manifest = convert_clitoolbench_all(freeze_out, dest_root, stdout_match=stdout_match)
    except ConvertError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for row in manifest["kept"]:
        print(f"kept {row['task']} as {row['id']} ({row['cases']} cases, {row['replay_s']}s)")
    for row in manifest["dropped"]:
        print(f"dropped {row['task']} at {row['stage']}: {row['reason']}")
    print(f"wrote {dest_root / MANIFEST}")
    return 0


def _warn_flags(dest: Path) -> None:
    provenance = json.loads((dest / "provenance.json").read_text(encoding="utf-8"))
    for flag in provenance["flags"]:
        detail = f" ({', '.join(provenance['oracle']['deps'])})" if "third_party" in flag else ""
        print(f"warning: {dest.name}: {flag}{detail}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
