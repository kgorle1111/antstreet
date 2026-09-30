import dataclasses
import json

import pytest

from boss.termsheet import CheckSpec, Round, Task, TermSheet, TermSheetError, validate

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


def test_valid_sheet_passes(checks_dir):
    validate(sheet(), checks_dir)


def test_json_round_trip(checks_dir):
    original = sheet()
    assert TermSheet.from_json(original.to_json()) == original


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"checks": ()}, "no checks"),
        ({"idea": "  "}, "idea is empty"),
        ({"budget_micros": 250_000}, "round budgets sum to 300000, term sheet budget is 250000"),
        ({"rounds": (Round(1, 300_000, 2), Round(3, 1, 2))}, "numbered 1, 2, 3"),
        ({"rounds": (Round(1, 100_000, 2), Round(2, 200_000, 1))}, "must not decrease"),
        ({"rounds": (Round(1, 300_000, 1),)}, "every check passes"),
        ({"rounds": (Round(1, 300_000, 5),)}, "between 1 and the number of checks"),
    ],
    ids=["no-checks", "empty-idea", "budget-sum", "numbering", "decreasing", "last-round", "range"],
)
def test_structural_problems(checks_dir, overrides, expected):
    assert any(expected in p for p in problems(sheet(**overrides), checks_dir))


def test_orphan_check_and_idle_task_are_both_reported(checks_dir):
    s = sheet(
        checks=(
            CheckSpec("c01", "d", "test_c01.py", "t9"),
            CheckSpec("c02", "d", "test_c02.py", "t1"),
        ),
        tasks=(Task("t1", "b", ("rev.py",)), Task("t2", "b", ("other.py",))),
    )
    found = problems(s, checks_dir)
    assert "check c01 belongs to unknown task 't9'" in found
    assert "task t2 owns no checks, so its progress cannot be measured" in found


def test_duplicate_ids(checks_dir):
    dup = CheckSpec("c01", "d", "test_c02.py", "t1")
    assert "duplicate check id 'c01'" in problems(
        sheet(checks=(sheet().checks[0], dup)), checks_dir
    )


@pytest.mark.parametrize("path", ["/etc/passwd", "../outside.py", ""])
def test_task_paths_must_stay_inside_the_workspace(checks_dir, path):
    s = sheet(tasks=(Task("t1", "b", (path,)),))
    assert any("must stay inside the workspace" in p for p in problems(s, checks_dir))


def test_check_file_problems(checks_dir):
    (checks_dir / "test_c02.py").write_text("def helper(:\n")
    (checks_dir / "test_c03.py").write_text("def helper():\n    return 1\n")
    s = sheet(
        checks=(
            CheckSpec("c01", "d", "../escape.py", "t1"),
            CheckSpec("c02", "d", "test_c02.py", "t1"),
            CheckSpec("c03", "d", "test_c03.py", "t1"),
            CheckSpec("c04", "d", "test_missing.py", "t1"),
        ),
        rounds=(Round(1, 300_000, 4),),
    )
    found = problems(s, checks_dir)
    assert "check c01 file '../escape.py' must be named test_<name>.py" in found
    assert any(p.startswith("check c02 has a syntax error") for p in found)
    assert "check c03 defines no test_ function" in found
    assert "check c04 file test_missing.py does not exist" in found


def test_test_class_counts_as_a_test(checks_dir):
    (checks_dir / "test_c02.py").write_text(
        "from rev import reverse\n\nclass TestHelpers:\n    pass\n\n"  # a Test* class with no tests first
        "class TestRev:\n    def test_empty(self):\n        assert reverse('') == ''\n"
    )
    validate(sheet(), checks_dir)


def test_check_that_passes_before_any_work_is_rejected(checks_dir):
    (checks_dir / "test_c02.py").write_text("def test_nothing():\n    assert True\n")
    assert problems(sheet(), checks_dir) == ["check c02 passes on an empty workspace"]


def test_gate_is_not_run_when_the_structure_is_broken(checks_dir):
    (checks_dir / "test_c02.py").write_text("def test_nothing():\n    assert True\n")
    found = problems(sheet(idea=""), checks_dir)
    assert found == ["idea is empty"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("tasks"),
        lambda d: d.update(extra=1),
        lambda d: d["rounds"][0].update(n="1"),
        lambda d: d["rounds"][0].update(budget_micros=True),
        lambda d: d["checks"][0].pop("task"),
        lambda d: d["tasks"][0].update(paths=[3]),
        lambda d: d.update(approved_by_investor="yes"),
    ],
    ids=["missing", "extra", "str-int", "bool-int", "check-missing", "path-type", "approved-type"],
)
def test_malformed_json_is_a_term_sheet_error(mutate):
    raw = json.loads(sheet().to_json())
    mutate(raw)
    with pytest.raises(TermSheetError, match="not a valid term sheet"):
        TermSheet.from_json(json.dumps(raw))


def test_records_are_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        sheet().idea = "changed"  # type: ignore[misc]
