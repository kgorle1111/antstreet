"""Term-sheet edge cases: hostile JSON, empty structures, odd check files, empty-workspace runs."""

import json

import pytest

from boss import termsheet
from boss.gate import Check
from boss.termsheet import (
    CheckSpec,
    Round,
    Task,
    TermSheet,
    TermSheetError,
    check_file_problems,
    validate,
)

GOOD_CHECK = "from rev import reverse\n\ndef test_reverses():\n    assert reverse('ab') == 'ba'\n"


def sheet(**overrides) -> TermSheet:
    base = {
        "idea": "A function that reverses a string.",
        "budget_micros": 300_000,
        "rounds": (Round(1, 100_000, 1), Round(2, 200_000, 2)),
        "checks": (
            CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
            CheckSpec("c02", "reverses empty", "test_c02.py", "t1"),
        ),
        "tasks": (Task("t1", "Write rev.py with reverse(s).", ("rev.py",)),),
    }
    return TermSheet(**(base | overrides))


@pytest.fixture
def checks_dir(tmp_path):
    d = tmp_path / "checks"
    d.mkdir()
    (d / "test_c01.py").write_text(GOOD_CHECK)
    (d / "test_c02.py").write_text(
        "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
    )
    return d


def problems(s: TermSheet, checks_dir) -> list[str]:
    with pytest.raises(TermSheetError) as info:
        validate(s, checks_dir)
    return info.value.problems


def spec_problems(checks_dir, file="test_x.py", source: bytes | str = GOOD_CHECK) -> list[str]:
    path = checks_dir / file
    path.write_bytes(source if isinstance(source, bytes) else source.encode())
    return check_file_problems(CheckSpec("cx", "d", file, "t1"), checks_dir)


# --- TermSheetError and small helpers ------------------------------------------------------


def test_error_message_joins_every_problem_and_keeps_the_list():
    err = TermSheetError(["one", "two"])
    assert str(err) == "one; two"
    assert err.problems == ["one", "two"]


def test_gate_checks_map_ids_to_files_in_order():
    assert sheet().gate_checks() == [Check("c01", "test_c01.py"), Check("c02", "test_c02.py")]


@pytest.mark.parametrize(
    "build",
    [
        lambda: Round(True, 1, 1),
        lambda: Round(1, 1.5, 1),
        lambda: CheckSpec("c", 3, "test_a.py", "t"),
        lambda: Task("t", "b", ["list", "not", "tuple"]),
        lambda: Task("t", "b", ("ok", 3)),
        lambda: sheet(approved_by_investor=1),
        lambda: sheet(rounds=[Round(1, 300_000, 2)]),
    ],
    ids=[
        "bool-int",
        "float-int",
        "int-str",
        "list-paths",
        "non-str-path",
        "int-bool",
        "list-rounds",
    ],
)
def test_wrong_types_are_refused_at_construction(build):
    with pytest.raises(TypeError):
        build()


# --- from_json against hostile input --------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["", "   ", "null", "[]", '"sheet"', "7", "{", '{"idea": "x"}'],
    ids=["empty", "blank", "null", "list", "string", "number", "truncated", "missing-fields"],
)
def test_json_that_is_not_a_term_sheet_object_is_a_term_sheet_error(text):
    with pytest.raises(TermSheetError, match="not a valid term sheet"):
        TermSheet.from_json(text)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(rounds={"1": {}}),
        lambda d: d.update(rounds=["not an object"]),
        lambda d: d.update(checks=[None]),
        lambda d: d.update(tasks="t1"),
        lambda d: d["tasks"][0].update(paths=5),
        lambda d: d["tasks"][0].update(paths=None),
        lambda d: d["rounds"][0].update(extra=1),
        lambda d: d.update(idea=["x"]),
        lambda d: d.update(budget_micros=1.5),
    ],
    ids=[
        "rounds-dict",
        "round-not-object",
        "check-null",
        "tasks-string",
        "paths-int",
        "paths-null",
        "round-extra-field",
        "idea-list",
        "float-budget",
    ],
)
def test_more_malformed_json_shapes_are_term_sheet_errors(mutate):
    raw = json.loads(sheet().to_json())
    mutate(raw)
    with pytest.raises(TermSheetError, match="not a valid term sheet"):
        TermSheet.from_json(json.dumps(raw))


def test_error_names_the_offending_record_type():
    raw = json.loads(sheet().to_json())
    raw["checks"][0]["extra"] = 1
    with pytest.raises(TermSheetError, match="CheckSpec fields differ: \\['extra'\\]"):
        TermSheet.from_json(json.dumps(raw))


def test_a_string_where_a_paths_list_belongs_is_refused_not_split_into_letters():
    raw = json.loads(sheet().to_json())
    raw["tasks"][0]["paths"] = "src/app.py"
    with pytest.raises(TermSheetError):
        TermSheet.from_json(json.dumps(raw))


def test_json_round_trip_keeps_unicode_and_the_approval_flag():
    original = sheet(idea="Umkehren: café ✓", approved_by_investor=True)
    assert TermSheet.from_json(original.to_json()) == original


# --- structure ------------------------------------------------------------------------------


def test_an_empty_sheet_reports_each_missing_part_once_and_never_crashes(checks_dir):
    empty = sheet(idea=" ", budget_micros=1, rounds=(), checks=(), tasks=())
    assert problems(empty, checks_dir) == [
        "idea is empty",
        "no checks",
        "no tasks",
        "no rounds",
        "round budgets sum to 0, term sheet budget is 1",
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"budget_micros": 0, "rounds": (Round(1, 0, 2),)},
        {"budget_micros": -5, "rounds": (Round(1, -5, 2),)},
        {"rounds": (Round(1, 300_001, 1), Round(2, -1, 2))},
    ],
    ids=["zero", "negative", "one-negative-round"],
)
def test_non_positive_budgets_are_one_clear_problem(checks_dir, overrides):
    found = problems(sheet(**overrides), checks_dir)
    assert "budgets must be positive integers (micro-dollars)" in found
    assert not any("round budgets sum" in p for p in found)


def test_a_task_with_no_paths_is_reported(checks_dir):
    found = problems(sheet(tasks=(Task("t1", "b", ()),)), checks_dir)
    assert found == ["task t1 declares no paths"]


@pytest.mark.parametrize("bad_id", ["", "has space", "x" * 33, "a/b", "oké", " c01"])
def test_invalid_ids_are_reported_for_checks_and_tasks(checks_dir, bad_id):
    s = sheet(
        checks=(CheckSpec(bad_id, "d", "test_c01.py", bad_id), sheet().checks[1]),
        tasks=(Task(bad_id, "b", ("rev.py",)), Task("t2", "b", ("other.py",))),
    )
    found = problems(s, checks_dir)
    assert f"check id {bad_id!r} is invalid" in found
    assert f"task id {bad_id!r} is invalid" in found


@pytest.mark.parametrize("good_id", ["c", "C_1-x", "9" * 32])
def test_boundary_ids_are_valid(checks_dir, good_id):
    s = sheet(
        checks=(
            CheckSpec(good_id, "d", "test_c01.py", good_id),
            CheckSpec("c02", "d", "test_c02.py", good_id),
        ),
        tasks=(Task(good_id, "b", ("rev.py",)),),
    )
    validate(s, checks_dir)


@pytest.mark.xfail(
    strict=True,
    reason="termsheet.py:_ID_RE ends in $, which also matches before a trailing newline",
)
def test_an_id_with_a_trailing_newline_is_invalid(checks_dir):
    s = sheet(
        checks=(
            CheckSpec("c01\n", "d", "test_c01.py", "t1\n"),
            CheckSpec("c02", "d", "test_c02.py", "t1\n"),
        ),
        tasks=(Task("t1\n", "b", ("rev.py",)),),
    )
    assert "check id 'c01\\n' is invalid" in problems(s, checks_dir)


def test_every_duplicate_id_is_named_once_however_often_it_repeats(checks_dir):
    dup = tuple(CheckSpec("c01", "d", "test_c01.py", "t1") for _ in range(3))
    found = problems(sheet(checks=dup, rounds=(Round(1, 300_000, 3),)), checks_dir)
    assert found.count("duplicate check id 'c01'") == 1


def test_duplicate_task_ids_are_reported(checks_dir):
    tasks = (Task("t1", "b", ("a.py",)), Task("t1", "b", ("b.py",)))
    assert "duplicate task id 't1'" in problems(sheet(tasks=tasks), checks_dir)


def test_two_checks_may_share_a_file(checks_dir):
    both = (
        CheckSpec("c01", "d", "test_c01.py", "t1"),
        CheckSpec("c02", "d", "test_c01.py", "t1"),
    )
    validate(sheet(checks=both), checks_dir)


# --- check files ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "file",
    [
        "c01.py",
        "test_.py",
        "test_a.txt",
        "test_a-b.py",
        "sub/test_a.py",
        "test_a.py.bak",
        "Test_a.py",
    ],
)
def test_check_file_names_must_match_the_pattern(checks_dir, file):
    found = check_file_problems(CheckSpec("cx", "d", file, "t1"), checks_dir)
    assert found == [f"check cx file {file!r} must be named test_<name>.py"]


def test_a_directory_with_a_test_name_is_reported_as_missing(checks_dir):
    (checks_dir / "test_dir.py").mkdir()
    found = check_file_problems(CheckSpec("cx", "d", "test_dir.py", "t1"), checks_dir)
    assert found == ["check cx file test_dir.py does not exist"]


def test_an_empty_check_file_defines_no_test(checks_dir):
    assert spec_problems(checks_dir, source="") == ["check cx defines no test_ function"]


def test_async_tests_and_test_prefixed_names_count(checks_dir):
    assert spec_problems(checks_dir, source="async def test_a():\n    pass\n") == []
    assert spec_problems(checks_dir, source="def testing():\n    pass\n") == []


def test_a_test_class_without_test_methods_does_not_count(checks_dir):
    src = (
        "class TestNothing:\n    x = 1\n\nclass Helper:\n    def test_hidden(self):\n        pass\n"
    )
    assert spec_problems(checks_dir, source=src) == ["check cx defines no test_ function"]


def test_a_test_method_in_a_non_test_class_does_not_count_for_the_class_rule(checks_dir):
    src = "class Helper:\n    def test_x(self):\n        pass\n"
    assert spec_problems(checks_dir, source=src) == ["check cx defines no test_ function"]


def test_null_bytes_are_a_syntax_problem_not_a_crash(checks_dir):
    found = spec_problems(checks_dir, source=b"def test_x():\n    pass\n\0")
    assert found == [
        "check cx has a syntax error: line None: source code string cannot contain null bytes"
    ]


def test_absurdly_nested_source_is_a_syntax_problem_not_a_crash(checks_dir):
    src = "x = " + "[" * 300 + "]" * 300 + "\ndef test_x():\n    pass\n"
    found = spec_problems(checks_dir, source=src)
    assert found == ["check cx has a syntax error: line 1: too many nested parentheses"]


def test_a_check_file_that_is_not_utf8_is_a_problem_not_a_crash(checks_dir):
    found = spec_problems(checks_dir, source=b"def test_x():\n    pass\n# caf\xe9\n")
    assert len(found) == 1


def test_a_check_file_with_a_utf8_bom_is_accepted(checks_dir):
    assert spec_problems(checks_dir, source=b"\xef\xbb\xbfdef test_x():\n    pass\n") == []


@pytest.mark.xfail(
    strict=True,
    reason="termsheet.py:validate: gate.run_gate raises GateError for a check symlinked outside "
    "the checks dir, and validate only converts structural problems into TermSheetError",
)
def test_a_check_symlinked_outside_the_checks_dir_is_a_problem_not_a_gate_crash(
    checks_dir, tmp_path
):
    outside = tmp_path / "outside.py"
    outside.write_text("def test_x():\n    assert False\n")
    (checks_dir / "test_c02.py").unlink()
    (checks_dir / "test_c02.py").symlink_to(outside)
    with pytest.raises(TermSheetError):
        validate(sheet(), checks_dir)


# --- the empty-workspace run ----------------------------------------------------------------


def test_a_check_that_hangs_on_an_empty_workspace_is_reported_as_a_timeout(checks_dir, monkeypatch):
    (checks_dir / "test_c02.py").write_text("import time\n\ndef test_hang():\n    time.sleep(30)\n")
    real = termsheet.run_gate
    monkeypatch.setattr(
        termsheet, "run_gate", lambda ws, cd, checks, timeout_s: real(ws, cd, checks, timeout_s=1)
    )
    assert problems(sheet(), checks_dir) == ["check c02 times out on an empty workspace"]


def test_passing_and_hanging_checks_are_both_reported_in_sheet_order(checks_dir, monkeypatch):
    (checks_dir / "test_c01.py").write_text("import time\n\ndef test_hang():\n    time.sleep(30)\n")
    (checks_dir / "test_c02.py").write_text("def test_ok():\n    assert True\n")
    real = termsheet.run_gate
    monkeypatch.setattr(
        termsheet, "run_gate", lambda ws, cd, checks, timeout_s: real(ws, cd, checks, timeout_s=1)
    )
    assert problems(sheet(), checks_dir) == [
        "check c01 times out on an empty workspace",
        "check c02 passes on an empty workspace",
    ]


def test_the_empty_workspace_run_uses_a_thirty_second_limit(checks_dir, monkeypatch):
    seen = {}

    def spy(ws, cd, checks, timeout_s):
        seen["timeout_s"] = timeout_s
        seen["ws_is_empty"] = not any(ws.iterdir())
        return []

    monkeypatch.setattr(termsheet, "run_gate", spy)
    validate(sheet(), checks_dir)
    assert seen == {"timeout_s": 30.0, "ws_is_empty": True}
