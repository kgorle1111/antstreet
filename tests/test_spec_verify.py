"""boss.spec.verify and render_report on hand-made drafts: a claim is reported beside what the
claiming checks contain, and an unverifiable claim is never counted as verified."""

import pytest

from boss import spec
from boss.spec import MAX_RULES_PER_CHECK, draft_gaps, render_report, split, verify

IDEA = (
    "Create `t.py` with `f(x)`.\n\n"
    "1. Non-ASCII digits are not valid and raise `ValueError`.\n"
    "2. `f(x)` returns the number as a `float`.\n"
    "3. A chain of 2000 operands must work.\n"
    "4. Spaces are trimmed."
)
S = split(IDEA)
R_ASCII, R_FLOAT, R_CHAIN, R_PLAIN = "R02", "R03", "R04", "R05"

GOOD_ASCII = (
    "import pytest\nfrom t import f\n\ndef test_a():\n    with pytest.raises(ValueError):\n"
    "        f('٣')\n"
)
ASCII_ONLY = (
    "import pytest\nfrom t import f\n\ndef test_a():\n    with pytest.raises(ValueError):\n"
    "        f('x')\n"
)
GOOD_FLOAT = "from t import f\n\ndef test_b():\n    assert isinstance(f('1'), float)\n"
INT_VALUE = "from t import f\n\ndef test_b():\n    assert f('1') == 1.0\n"
GOOD_CHAIN = "from t import f\n\ndef test_c():\n    assert f('+'.join(['1'] * 2000)) == 2000\n"
SHORT_CHAIN = "from t import f\n\ndef test_c():\n    assert f('+'.join(['1'] * 100)) == 100\n"
PLAIN = "from t import f\n\ndef test_d():\n    assert f(' 1 ') == 1\n"


def statuses(report):
    return {s.rule: s.state for s in report.statuses}


def test_the_rules_of_the_hand_made_idea_are_what_the_tests_below_assume():
    assert [(r.id, r.scored) for r in S.rules] == [
        ("R01", False),
        ("R02", True),
        ("R03", True),
        ("R04", True),
        ("R05", True),
    ]
    assert [a.type for a in S.by_id()[R_ASCII].anchors] == ["exception", "non_ascii"]
    assert [a.type for a in S.by_id()[R_FLOAT].anchors] == ["type"]
    assert [a.type for a in S.by_id()[R_CHAIN].anchors] == ["magnitude"]


def test_a_draft_that_cites_nothing_leaves_every_scored_rule_uncovered():
    report = verify(S, {}, {})
    assert statuses(report) == {
        "R01": "context",
        "R02": "uncovered",
        "R03": "uncovered",
        "R04": "uncovered",
        "R05": "uncovered",
    }
    assert report.headline == 0 and report.claimed == 0 and report.problems == ()


def test_a_claim_whose_checks_hold_every_anchor_is_anchored_and_one_with_no_anchor_is_unanchored():
    report = verify(
        S,
        {"c01": [R_ASCII], "c02": [R_FLOAT], "c03": [R_CHAIN], "c04": [R_PLAIN]},
        {"c01": GOOD_ASCII, "c02": GOOD_FLOAT, "c03": GOOD_CHAIN, "c04": PLAIN},
    )
    assert statuses(report) | {"R01": "x"} == {
        "R01": "x",
        "R02": "anchored",
        "R03": "anchored",
        "R04": "anchored",
        "R05": "unanchored",
    }
    assert report.headline == 3 / 4, "an unanchored claim is not counted as verified"
    assert report.claimed == 4


def test_a_claim_the_check_cannot_be_testing_is_anchor_missing_and_names_what_is_absent():
    report = verify(
        S,
        {"c01": [R_ASCII], "c02": [R_FLOAT], "c03": [R_CHAIN]},
        {"c01": ASCII_ONLY, "c02": INT_VALUE, "c03": SHORT_CHAIN},
    )
    by = {s.rule: s for s in report.statuses}
    assert [by[r].state for r in (R_ASCII, R_FLOAT, R_CHAIN)] == ["anchor_missing"] * 3
    assert [a.type for a in by[R_ASCII].missing] == ["non_ascii"]
    assert [a.type for a in by[R_FLOAT].missing] == ["type"]
    assert report.headline == 0 and report.claimed == 3, "claimed reads 3/4 while anchored reads 0"


def test_anchors_are_pooled_over_the_checks_that_claim_the_rule_not_over_all_checks():
    pooled = verify(
        S,
        {"c01": [R_ASCII], "c02": [R_ASCII]},
        {"c01": ASCII_ONLY, "c02": "def test_z():\n    assert f('٣')\n"},
    )
    assert statuses(pooled)[R_ASCII] == "anchored"
    elsewhere = verify(
        S,
        {"c01": [R_ASCII], "c02": [R_PLAIN]},
        {"c01": ASCII_ONLY, "c02": "def test_z():\n    assert f('٣')\n"},
    )
    assert statuses(elsewhere)[R_ASCII] == "anchor_missing", (
        "a check that does not claim it is no help"
    )


def test_a_waived_rule_is_reported_apart_and_never_counted_covered():
    report = verify(S, {"c01": [R_FLOAT]}, {"c01": GOOD_FLOAT}, waived={R_PLAIN: "an example"})
    assert statuses(report)[R_PLAIN] == "waived"
    assert report.count("uncovered") == 2 and report.headline == 1 / 4
    assert report.to_summary()["waived"] == [R_PLAIN]


def test_waiving_most_of_the_rules_is_a_warning():
    reasons = {R_ASCII: "x", R_FLOAT: "y"}
    assert any("untested" in w for w in verify(S, {}, {}, waived=reasons).warnings)
    assert verify(S, {}, {}, waived={R_PLAIN: "z"}).warnings == ()


@pytest.mark.parametrize(
    ("claims", "waived", "problem"),
    [
        ({"c01": ["R99"]}, {}, "unknown rule 'R99'"),
        ({"c01": []}, {}, "cites no rule"),
        ({"c01": [R_FLOAT, R_FLOAT]}, {}, "cites a rule twice"),
        ({"c01": [R_FLOAT]}, {R_FLOAT: "why"}, "cited by c01 and untested"),
        ({}, {"R99": "why"}, "untested names unknown rule 'R99'"),
        (
            {"c01": ["R01", "R02", "R03", "R04", "R05", "R06"]},
            {},
            f"at most {MAX_RULES_PER_CHECK}",
        ),
    ],
)
def test_a_structure_a_draft_must_not_have_is_a_problem(claims, waived, problem):
    report = verify(S, claims, {}, waived=waived)
    assert any(problem in p for p in report.problems), report.problems


def test_every_problem_is_listed_not_just_the_first():
    report = verify(S, {"c01": [], "c02": ["R99"]}, {})
    assert len(report.problems) == 2


def test_a_claiming_check_that_does_not_parse_is_unreadable_and_its_anchors_are_missing():
    report = verify(S, {"c01": [R_ASCII]}, {"c01": "def test_a(:\n"})
    assert statuses(report)[R_ASCII] == "anchor_missing"
    assert report.unreadable == ("c01",)
    assert verify(S, {"c01": [R_ASCII]}, {}).unreadable == ("c01",), "no source at all"


def test_a_claim_on_a_context_rule_is_tolerated_and_not_scored():
    report = verify(S, {"c01": ["R01", R_FLOAT]}, {"c01": GOOD_FLOAT})
    assert statuses(report)["R01"] == "context"
    assert report.problems == ()
    assert report.scorable == 4


def test_a_coarse_split_warns_that_coverage_is_per_group():
    idea = "\n".join(f"{n}. First {n}. Second {n}. Third {n}." for n in range(1, 21))
    assert any("long" in w for w in verify(split(idea), {}, {}).warnings)


def test_the_union_form_lists_rules_whose_anchors_no_check_of_the_draft_contains():
    sources = {"c01": ASCII_ONLY, "c02": INT_VALUE, "c03": GOOD_CHAIN}
    gaps = draft_gaps(S, sources)
    assert sorted(gaps) == [R_ASCII, R_FLOAT]
    assert [a.type for a in gaps[R_ASCII]] == ["non_ascii"]
    assert draft_gaps(S, {**sources, "c04": GOOD_ASCII, "c05": GOOD_FLOAT}) == {}


def test_the_summary_for_the_ledger_has_counts_ids_and_the_rule_list_digest():
    report = verify(S, {"c01": [R_FLOAT]}, {"c01": INT_VALUE})
    summary = report.to_summary()
    assert summary["rules_sha256"] == spec.rules_digest(S)
    assert summary["rules"] == 4 and summary["anchor_missing"] == 1
    assert summary["uncovered"] == [R_ASCII, R_CHAIN, R_PLAIN]


def test_the_view_lists_uncovered_rules_first_and_shows_both_the_claim_and_the_evidence():
    report = verify(
        S,
        {"c01": [R_FLOAT], "c02": [R_CHAIN]},
        {"c01": INT_VALUE, "c02": GOOD_CHAIN},
        waived={R_PLAIN: "just prose"},
    )
    view = render_report(report, {R_PLAIN: "just prose"})
    lines = view.splitlines()
    assert lines[0].startswith("SPEC COVERAGE  rules 4 | UNCOVERED 1 | anchored 1")
    assert "anchored 25%; claimed 2/4" in lines[0]
    order = [
        view.index(h) for h in ("UNCOVERED (no check", "CLAIMED, BUT", "WAIVED", "ANCHORS PRESENT")
    ]
    assert order == sorted(order)
    assert "R02 [error] Non-ASCII digits are not valid" in view
    assert "-> c01: no float (name)" in view
    assert "(boss, unverified: just prose)" in view


def test_the_view_makes_hostile_idea_text_and_a_hostile_reason_safe_to_print():
    idea = "1. It rejects \x1b[2J and ‮ evil. Next rule."
    report = verify(split(idea), {}, {}, waived={"R02": "a\nb\x1b[31m"})
    view = render_report(report, {"R02": "a\nb\x1b[31m"})
    assert "\x1b" not in view and "‮" not in view
    assert "\\x1b" in view and "\\u202e" in view
    assert "a b" in view, "a reason is one line"


def test_the_view_of_an_empty_idea_does_not_divide_by_zero():
    report = verify(split(""), {}, {})
    assert report.headline == 0
    assert "rules 0" in render_report(report)
