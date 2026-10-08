"""A check may name the acceptance criteria it verifies, without changing how any older term
sheet serialises: approval hashes cover that JSON."""

import dataclasses
import hashlib
import json

import pytest

from antstreet.termsheet import CheckSpec, Round, Task, TermSheet, TermSheetError

# Produced by the code as it was BEFORE CheckSpec had a `criteria` field.
BEFORE = """{
  "idea": "Reverse a string.",
  "budget_micros": 500000,
  "rounds": [
    {
      "n": 1,
      "budget_micros": 200000,
      "unlock_checks": 1
    },
    {
      "n": 2,
      "budget_micros": 300000,
      "unlock_checks": 2
    }
  ],
  "checks": [
    {
      "id": "c01",
      "description": "reverses a word",
      "file": "test_c01.py",
      "task": "t1"
    },
    {
      "id": "c02",
      "description": "empty",
      "file": "test_c02.py",
      "task": "t2"
    }
  ],
  "tasks": [
    {
      "id": "t1",
      "brief": "Create rev.py",
      "paths": [
        "rev.py"
      ]
    },
    {
      "id": "t2",
      "brief": "Create up.py",
      "paths": [
        "up.py",
        "pkg"
      ]
    }
  ],
  "approved_by_investor": false
}"""
BEFORE_SHA256 = "917066ece5af89954c4cd4a01a2ecf17128cffe6bf675c74372f99c6dcc0d10a"


def sheet(*criteria: tuple[str, ...]) -> TermSheet:
    c1, c2 = criteria or ((), ())
    return TermSheet(
        "Reverse a string.",
        500_000,
        (Round(1, 200_000, 1), Round(2, 300_000, 2)),
        (
            CheckSpec("c01", "reverses a word", "test_c01.py", "t1", c1),
            CheckSpec("c02", "empty", "test_c02.py", "t2", c2),
        ),
        (
            Task("t1", "Create rev.py", ("rev.py",)),
            Task("t2", "Create up.py", ("up.py", "pkg")),
        ),
    )


def test_a_sheet_whose_checks_name_no_criteria_serialises_exactly_as_it_did_before():
    text = sheet().to_json()
    assert text == BEFORE
    assert hashlib.sha256(text.encode()).hexdigest() == BEFORE_SHA256


def test_a_sheet_written_before_the_field_existed_still_loads():
    loaded = TermSheet.from_json(BEFORE)
    assert loaded == sheet()
    assert all(c.criteria == () for c in loaded.checks)


def test_criteria_are_written_only_for_the_checks_that_have_some_and_round_trip():
    original = sheet(("S1.1", "S2.3"), ())
    raw = json.loads(original.to_json())
    assert raw["checks"][0]["criteria"] == ["S1.1", "S2.3"]
    assert "criteria" not in raw["checks"][1]
    assert TermSheet.from_json(original.to_json()) == original


def test_criteria_change_the_serialised_sheet_so_an_approval_cannot_survive_a_relabelling():
    assert sheet(("S1.1",), ()).to_json() != sheet(("S1.2",), ()).to_json()
    assert sheet(("S1.1",), ()).to_json() != BEFORE


@pytest.mark.parametrize(
    "bad",
    [
        ("S1",),
        ("s1.1",),
        ("S1.0",),
        ("S0.1",),
        ("S1.1 ",),
        ("S1.1\n",),
        ("",),
        ("1.1",),
        ("S1.1.1",),
        ("R00",),
        ("R1",),
        ("R100",),
        ("r01",),
        ("R01 ",),
        ("R01\n",),
        ("R01.1",),
    ],
)
def test_a_malformed_criterion_id_is_refused(bad):
    with pytest.raises(ValueError, match="not a criterion id"):
        CheckSpec("c01", "d", "test_c01.py", "t1", bad)


def test_criteria_must_be_a_tuple_of_text_without_repeats():
    with pytest.raises(TypeError):
        CheckSpec("c01", "d", "test_c01.py", "t1", ["S1.1"])
    with pytest.raises(ValueError, match="not a criterion id"):
        CheckSpec("c01", "d", "test_c01.py", "t1", (11,))
    with pytest.raises(ValueError, match="repeats"):
        CheckSpec("c01", "d", "test_c01.py", "t1", ("S1.1", "S1.1"))


@pytest.mark.parametrize("value", ["S1.1", ["S1"], [1], None, {"a": 1}])
def test_a_hostile_criteria_field_in_json_is_a_term_sheet_error(value):
    raw = json.loads(sheet(("S1.1",), ()).to_json())
    raw["checks"][0]["criteria"] = value
    with pytest.raises(TermSheetError, match="not a valid term sheet"):
        TermSheet.from_json(json.dumps(raw))


def test_an_unknown_extra_field_is_still_refused_and_a_missing_required_one_still_named():
    raw = json.loads(BEFORE)
    raw["checks"][0]["priority"] = "must"
    with pytest.raises(TermSheetError, match=r"fields differ: \['priority'\]"):
        TermSheet.from_json(json.dumps(raw))
    raw = json.loads(BEFORE)
    del raw["checks"][0]["task"]
    with pytest.raises(TermSheetError, match=r"fields differ: \['task'\]"):
        TermSheet.from_json(json.dumps(raw))


def test_replacing_the_criteria_of_a_check_keeps_the_other_fields():
    check = dataclasses.replace(sheet().checks[0], criteria=("S1.1",))
    assert (check.id, check.file, check.task, check.criteria) == (
        "c01",
        "test_c01.py",
        "t1",
        ("S1.1",),
    )


@pytest.mark.parametrize("good", [("R01",), ("R09", "R10"), ("R99",), ("R01", "S1.1")])
def test_a_rule_id_of_the_request_is_a_criterion_id(good):
    assert CheckSpec("c01", "d", "test_c01.py", "t1", good).criteria == good
