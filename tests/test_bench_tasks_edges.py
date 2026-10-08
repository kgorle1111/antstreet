"""Benchmark task edge cases: malformed folders, reference imports, gate mapping, hashing."""

import json
from pathlib import Path

import pytest

from antstreet.bench import tasks as bench_tasks
from antstreet.bench.tasks import (
    MIN_HIDDEN_CHECKS,
    MIN_MUTANTS,
    BenchTask,
    TaskError,
    gate_problems,
    load_task,
    load_tasks,
    structural_problems,
    task_set_hash,
    validate_task,
)
from antstreet.gate import Check, CheckResult, CheckStatus

HIDDEN = "from demo import f\n\ndef test_x():\n    assert f() == 1\n"


def make_task(
    root: Path,
    task_id: str = "demo",
    *,
    title: str = "Demo",
    difficulty: str = "easy",
    idea: str | None = "Create demo.py with f().",
    hidden: int = MIN_HIDDEN_CHECKS,
    reference: str | None = "def f():\n    return 1\n",
    mutants: int = MIN_MUTANTS,
) -> Path:
    folder = root / task_id
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(
        json.dumps({"id": task_id, "title": title, "difficulty": difficulty})
    )
    if idea is not None:
        (folder / "idea.md").write_text(idea)
    (folder / "hidden_checks").mkdir()
    for n in range(hidden):
        (folder / "hidden_checks" / f"test_c{n}.py").write_text(HIDDEN)
    if reference is not None:
        (folder / "reference").mkdir()
        (folder / "reference" / "demo.py").write_text(reference)
    for n in range(mutants):
        (folder / "mutants" / f"wrong_{n}").mkdir(parents=True)
        (folder / "mutants" / f"wrong_{n}" / "demo.py").write_text(
            f"def f():\n    return {n + 2}\n"
        )
    return folder


def structural(folder: Path) -> list[str]:
    return structural_problems(load_task(folder))


def reference_problems(folder: Path) -> list[str]:
    """Only the problems about reference/: the mutants' own rules are tested elsewhere."""
    return [p for p in structural(folder) if p.startswith("reference/")]


def test_an_id_with_a_trailing_newline_is_refused(tmp_path):
    found = structural(make_task(tmp_path, "demo\n"))
    assert any("must be lowercase-with-dashes" in p for p in found)


def test_a_well_formed_task_has_no_structural_problems(tmp_path):
    assert structural(make_task(tmp_path)) == []


# --- meta.json and loading -------------------------------------------------------------------


def test_missing_meta_json_is_a_task_error_naming_the_folder(tmp_path):
    (tmp_path / "demo").mkdir()
    with pytest.raises(TaskError, match=r"task demo: meta\.json unreadable") as info:
        load_task(tmp_path / "demo")
    assert info.value.problems[0].startswith("meta.json unreadable")


def test_meta_json_that_is_not_utf8_is_a_task_error(tmp_path):
    folder = make_task(tmp_path)
    (folder / "meta.json").write_bytes(b'{"id": "\xff"}')
    with pytest.raises(TaskError, match="meta.json unreadable"):
        load_task(folder)


@pytest.mark.parametrize(
    "text",
    ["[]", "null", '"demo"', '{"id": "demo", "title": "t", "difficulty": "easy", "extra": 1}'],
    ids=["list", "null", "string", "extra-key"],
)
def test_meta_json_with_the_wrong_shape_names_the_required_keys(tmp_path, text):
    folder = make_task(tmp_path)
    (folder / "meta.json").write_text(text)
    with pytest.raises(TaskError, match=r"exactly the keys \['difficulty', 'id', 'title'\]"):
        load_task(folder)


@pytest.mark.parametrize("bad", [None, 3, ["easy"], True])
def test_every_meta_value_must_be_a_string(tmp_path, bad):
    folder = make_task(tmp_path)
    (folder / "meta.json").write_text(json.dumps({"id": "demo", "title": "t", "difficulty": bad}))
    with pytest.raises(TaskError, match="values must be strings"):
        load_task(folder)


def test_load_tasks_skips_folders_without_meta_and_plain_files_and_sorts(tmp_path):
    make_task(tmp_path, "zeta")
    make_task(tmp_path, "alpha")
    (tmp_path / "notes").mkdir()
    (tmp_path / "README.md").write_text("x")
    assert [t.id for t in load_tasks(tmp_path)] == ["alpha", "zeta"]


def test_one_malformed_task_fails_the_whole_listing(tmp_path):
    make_task(tmp_path, "alpha")
    make_task(tmp_path, "beta")
    (tmp_path / "beta" / "meta.json").write_text("{")
    with pytest.raises(TaskError, match="task beta"):
        load_tasks(tmp_path)


def test_a_missing_tasks_folder_is_an_os_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tasks(tmp_path / "nope")


def test_task_properties_point_into_the_folder_and_strip_the_idea(tmp_path):
    task = load_task(make_task(tmp_path, idea="\n  Create demo.py.  \n\n"))
    assert task.idea == "Create demo.py."
    assert task.hidden_dir == task.root / "hidden_checks"
    assert task.reference_dir == task.root / "reference"


def test_hidden_checks_are_named_from_their_files_sorted_and_only_test_py(tmp_path):
    folder = make_task(tmp_path, hidden=0)
    hidden = folder / "hidden_checks"
    for name in ("test_b.py", "test_a.py", "test_a_b.py", "helper.py", "conftest.py", "test_c.txt"):
        (hidden / name).write_text(HIDDEN)
    (hidden / "sub").mkdir()
    (hidden / "sub" / "test_nested.py").write_text(HIDDEN)
    assert load_task(folder).hidden_checks() == [
        Check("a", "test_a.py"),
        Check("a_b", "test_a_b.py"),
        Check("b", "test_b.py"),
    ]


def test_a_task_without_a_hidden_dir_has_no_hidden_checks(tmp_path):
    folder = make_task(tmp_path, hidden=0)
    (folder / "hidden_checks").rmdir()
    assert load_task(folder).hidden_checks() == []


# --- structure -------------------------------------------------------------------------------


@pytest.mark.parametrize("task_id", ["a", "Demo", "demo_x", "-demo", "de mo", "x" * 42])
def test_ids_outside_the_pattern_are_reported(tmp_path, task_id):
    folder = make_task(tmp_path, "ok-id")
    (folder / "meta.json").write_text(
        json.dumps({"id": task_id, "title": "t", "difficulty": "easy"})
    )
    found = structural(folder)
    assert f"id {task_id!r} must be lowercase-with-dashes and equal the folder name" in found


@pytest.mark.parametrize("task_id", ["ab", "a-b", "0a", "x" * 41])
def test_boundary_ids_are_accepted_when_the_folder_matches(tmp_path, task_id):
    assert structural(make_task(tmp_path, task_id)) == []


def test_a_blank_title_is_reported(tmp_path):
    assert structural(make_task(tmp_path, title=" \t")) == ["title is empty"]


def test_difficulty_must_be_one_of_the_three_levels(tmp_path):
    assert structural(make_task(tmp_path, difficulty="Easy")) == [
        "difficulty must be one of ('easy', 'medium', 'hard')"
    ]


@pytest.mark.parametrize("idea", [None, "", "  \n\t\n"], ids=["missing", "empty", "blank"])
def test_missing_or_blank_idea_stops_before_the_check_and_reference_rules(tmp_path, idea):
    folder = make_task(tmp_path, idea=idea, hidden=0, reference=None, title="")
    assert structural(folder) == ["title is empty", "idea.md is missing or empty"]


def test_an_idea_that_starts_with_a_dash_is_reported(tmp_path):
    assert structural(make_task(tmp_path, idea="- do a thing")) == [
        "idea.md must not start with '-'"
    ]


def test_an_idea_with_a_dash_only_after_stripping_leading_space_is_still_reported(tmp_path):
    assert structural(make_task(tmp_path, idea="\n\n-x")) == ["idea.md must not start with '-'"]


def test_test_code_in_the_idea_is_reported(tmp_path):
    found = structural(make_task(tmp_path, idea="Write f.\n\ndef test_it(): ..."))
    assert found == ["idea.md contains test code; hidden checks must stay hidden"]


def test_the_minimum_number_of_hidden_checks_is_enforced_exactly(tmp_path):
    assert structural(make_task(tmp_path, "one", hidden=MIN_HIDDEN_CHECKS - 1)) == [
        f"needs at least {MIN_HIDDEN_CHECKS} hidden checks, has {MIN_HIDDEN_CHECKS - 1}"
    ]
    assert structural(make_task(tmp_path, "two", hidden=MIN_HIDDEN_CHECKS + 3)) == []


def test_each_hidden_check_file_is_validated(tmp_path):
    folder = make_task(tmp_path)
    (folder / "hidden_checks" / "test_c0.py").write_text("def broken(:\n")
    (folder / "hidden_checks" / "test_c1.py").write_text("def helper():\n    pass\n")
    found = structural(folder)
    assert [p.split(":")[0] for p in found] == [
        "check c0 has a syntax error",
        "check c1 defines no test_ function",
    ]


@pytest.mark.parametrize("reference", [None, ""], ids=["no-folder", "empty-file"])
def test_a_missing_reference_is_reported(tmp_path, reference):
    folder = make_task(tmp_path, reference=reference)
    if reference == "":
        (folder / "reference" / "demo.py").unlink()
    assert structural(folder) == ["reference/ must contain the reference solution"]


def test_a_reference_with_a_syntax_error_is_reported_with_its_line(tmp_path):
    folder = make_task(tmp_path, reference="def f():\n    return 1\n\ndef g(:\n")
    assert reference_problems(folder) == ["reference/demo.py has a syntax error on line 4"]


def test_a_syntax_error_in_one_reference_file_does_not_hide_problems_in_another(tmp_path):
    folder = make_task(tmp_path)
    (folder / "reference" / "a_broken.py").write_text("def (\n")
    (folder / "reference" / "z_deps.py").write_text("import numpy\n")
    assert reference_problems(folder) == [
        "reference/a_broken.py has a syntax error on line 1",
        "reference/z_deps.py imports 'numpy', which is not stdlib",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "import os.path\nimport collections.abc\nfrom typing import Any\n",
        "from __future__ import annotations\n",
        "from . import sibling\nfrom .. import parent\n",
        "import demo_helper\n",
        "def f():\n    import json\n    return json\n",
    ],
    ids=["stdlib-dotted", "future", "relative", "sibling-module", "function-scope"],
)
def test_stdlib_relative_and_sibling_imports_are_allowed(tmp_path, source):
    folder = make_task(tmp_path)
    (folder / "reference" / "demo_helper.py").write_text("X = 1\n")
    (folder / "reference" / "demo.py").write_text(source + "def f():\n    return 1\n")
    assert reference_problems(folder) == []


@pytest.mark.parametrize(
    ("source", "module"),
    [
        ("import requests.adapters\n", "requests"),
        ("from numpy.linalg import norm\n", "numpy"),
        ("import os, yaml\n", "yaml"),
        ("try:\n    import attr\nexcept ImportError:\n    attr = None\n", "attr"),
        ("def f():\n    import pandas\n", "pandas"),
    ],
    ids=["dotted", "from-dotted", "second-of-two", "guarded", "function-scope"],
)
def test_third_party_imports_are_found_wherever_they_hide(tmp_path, source, module):
    folder = make_task(tmp_path, reference=source)
    assert reference_problems(folder) == [
        f"reference/demo.py imports {module!r}, which is not stdlib"
    ]


def test_each_third_party_module_is_reported_once_per_file_in_sorted_order(tmp_path):
    folder = make_task(tmp_path, reference="import zlib_ng\nimport aiofiles\nimport zlib_ng\n")
    assert reference_problems(folder) == [
        "reference/demo.py imports 'aiofiles', which is not stdlib",
        "reference/demo.py imports 'zlib_ng', which is not stdlib",
    ]


def test_only_top_level_reference_files_are_examined(tmp_path):
    folder = make_task(tmp_path)
    (folder / "reference" / "pkg").mkdir()
    (folder / "reference" / "pkg" / "mod.py").write_text("import numpy\n")
    assert reference_problems(folder) == []


# --- validate_task and the gate mapping -------------------------------------------------------


def result(check_id: str, status: CheckStatus, detail: str = "") -> CheckResult:
    return CheckResult(check_id, status, 0, detail, "", 0.0)


def fake_gate(monkeypatch, on_empty: list[CheckResult], on_reference: list[CheckResult]):
    calls = []

    def fake(workspace, checks_dir, checks, timeout_s):
        calls.append((Path(workspace).name, timeout_s))
        return on_reference if Path(workspace).name == "reference" else on_empty

    monkeypatch.setattr(bench_tasks, "run_gate", fake)
    return calls


def test_gate_problems_report_free_passes_and_timeouts_on_the_empty_workspace(
    tmp_path, monkeypatch
):
    folder = make_task(tmp_path)
    fake_gate(
        monkeypatch,
        on_empty=[
            result("c0", CheckStatus.FAILED),
            result("c1", CheckStatus.PASSED),
            result("c2", CheckStatus.TIMEOUT),
        ],
        on_reference=[result(f"c{n}", CheckStatus.PASSED) for n in range(3)],
    )
    assert gate_problems(load_task(folder)) == [
        "hidden check c1 does not fail on an empty workspace (passed)",
        "hidden check c2 does not fail on an empty workspace (timeout)",
    ]


def test_gate_problems_report_reference_failures_with_the_gates_detail(tmp_path, monkeypatch):
    folder = make_task(tmp_path, mutants=0)
    calls = fake_gate(
        monkeypatch,
        on_empty=[result("c0", CheckStatus.FAILED)],
        on_reference=[
            result("c0", CheckStatus.FAILED, "pytest exited 1"),
            result("c1", CheckStatus.TIMEOUT, "exceeded 30.0s"),
        ],
    )
    assert gate_problems(load_task(folder)) == [
        "hidden check c0 does not pass on the reference (pytest exited 1)",
        "hidden check c1 does not pass on the reference (exceeded 30.0s)",
    ]
    assert [seconds for _, seconds in calls] == [30.0, 30.0]


def test_the_empty_run_uses_an_empty_directory_and_the_reference_run_the_reference(
    tmp_path, monkeypatch
):
    folder = make_task(tmp_path, mutants=0)
    seen = []

    def fake(workspace, checks_dir, checks, timeout_s):
        seen.append((Path(workspace), list(Path(workspace).iterdir()), Path(checks_dir), checks))
        return []

    monkeypatch.setattr(bench_tasks, "run_gate", fake)
    gate_problems(load_task(folder))
    (empty_ws, empty_content, dir_a, checks_a), (ref_ws, _, dir_b, checks_b) = seen
    assert empty_content == []
    assert ref_ws == folder / "reference"
    assert dir_a == dir_b == folder / "hidden_checks"
    assert checks_a == checks_b and len(checks_a) == MIN_HIDDEN_CHECKS
    assert not empty_ws.exists()


def test_structural_problems_short_circuit_the_gate(tmp_path, monkeypatch):
    folder = make_task(tmp_path, title="")
    calls = fake_gate(monkeypatch, [], [])
    with pytest.raises(TaskError) as info:
        validate_task(load_task(folder))
    assert info.value.problems == ["title is empty"]
    assert calls == []


def test_a_valid_task_passes_through_both_stages(tmp_path, monkeypatch):
    folder = make_task(tmp_path)
    checks = [f"c{n}" for n in range(MIN_HIDDEN_CHECKS)]
    calls = fake_gate(
        monkeypatch,
        on_empty=[result(c, CheckStatus.FAILED) for c in checks],
        on_reference=[result(c, CheckStatus.PASSED) for c in checks],
    )
    validate_task(load_task(folder))
    assert len(calls) == 2 + MIN_MUTANTS  # empty workspace, reference, then each mutant


def test_task_error_message_names_the_task_and_joins_the_problems():
    err = TaskError("demo", ["one", "two"])
    assert str(err) == "task demo: one; two"
    assert err.problems == ["one", "two"]


# --- task_set_hash ---------------------------------------------------------------------------


def tasks_in(root: Path, *ids: str) -> list[BenchTask]:
    return [load_task(make_task(root, i)) for i in ids]


def test_hash_is_sixteen_hex_chars_and_independent_of_list_order(tmp_path):
    tasks = tasks_in(tmp_path, "alpha", "beta")
    digest = task_set_hash(tasks)
    assert len(digest) == 16 and int(digest, 16) >= 0
    assert task_set_hash(tasks[::-1]) == digest


def test_hash_of_no_tasks_is_the_empty_digest_prefix():
    assert task_set_hash([]) == "e3b0c44298fc1c14"


def test_hash_ignores_pycache_but_notices_renames_and_new_files(tmp_path):
    [task] = tasks_in(tmp_path, "alpha")
    before = task_set_hash([task])
    (task.root / "reference" / "__pycache__").mkdir()
    (task.root / "reference" / "__pycache__" / "demo.pyc").write_bytes(b"\0\1")
    assert task_set_hash([task]) == before
    (task.root / "extra.txt").write_text("x")
    added = task_set_hash([task])
    assert added != before
    (task.root / "extra.txt").rename(task.root / "extra2.txt")
    assert task_set_hash([task]) != added


def test_hash_depends_on_the_task_folder_name_not_just_the_bytes(tmp_path):
    a = load_task(make_task(tmp_path / "one", "alpha"))
    b = load_task(make_task(tmp_path / "two", "bravo"))
    assert task_set_hash([a]) != task_set_hash([b])


def test_hash_distinguishes_where_a_file_name_ends_and_its_content_begins(tmp_path):
    def task_with(root: Path, name: str, content: bytes) -> BenchTask:
        folder = root / "t1"
        folder.mkdir(parents=True)
        (folder / name).write_bytes(content)
        return BenchTask("t1", "t", "easy", folder)

    one = task_with(tmp_path / "one", "a", b"bc")
    other = task_with(tmp_path / "two", "ab", b"c")
    assert task_set_hash([one]) != task_set_hash([other])
