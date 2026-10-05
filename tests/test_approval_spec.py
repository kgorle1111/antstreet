"""The rule coverage in the investor's approval: what is shown, what is bound by the signature and
the hashes, and what a forger or a careless edit cannot do (docs/THREAT_MODEL.md, T55 to T57)."""

import dataclasses
import json

import pytest

from boss import spec
from boss.approval import (
    NotApprovedError,
    content_hashes,
    require_approval,
    review_term_sheet,
    spec_view,
)
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.rundir import RunPaths
from boss.termsheet import CheckSpec, Round, Task, TermSheet

IDEA = (
    "Create rev.py with reverse(s).\n\n"
    "1. reverse('') returns ''.\n"
    "2. A non-string raises `TypeError`.\n"
    "3. Case is kept."
)
EMPTY = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
TYPE_OK = (
    "import pytest\nfrom rev import reverse\n\ndef test_type():\n"
    "    with pytest.raises(TypeError):\n        reverse(3)\n"
)
TYPE_BAD = "from rev import reverse\n\ndef test_type():\n    assert reverse('ab') == 'ba'\n"
SHEET = TermSheet(
    idea=IDEA,
    budget_micros=500_000,
    rounds=(Round(1, 500_000, 2),),
    checks=(
        CheckSpec("c01", "empty", "test_c01.py", "t1", ("R02",)),
        CheckSpec("c02", "type", "test_c02.py", "t1", ("R03",)),
    ),
    tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
)


@pytest.fixture
def project(tmp_path):
    run = RunPaths(tmp_path / "project" / ".boss" / "runs" / "r1")
    run.checks.mkdir(parents=True)
    (run.checks / "test_c01.py").write_text(EMPTY)
    (run.checks / "test_c02.py").write_text(TYPE_OK)
    run.rules.write_text(spec.dumps(spec.split(IDEA)), encoding="utf-8")
    return run


def approve(run, sheet=SHEET, answers=("a",), edits=None, untested=None):
    said = []
    replies = iter(answers)
    count = []

    def ask(prompt):
        if edits and len(count) in edits:
            edits[len(count)]()
        count.append(prompt)
        return next(replies)

    with run.writer() as ledger:
        result = review_term_sheet(
            sheet,
            run.checks,
            run.root,
            ledger,
            "r1",
            ask=ask,
            say=said.append,
            spec_shown=spec_view(run.rules, run.checks, untested),
            rules_path=run.rules,
        )
    return result, said


def check(run, sheet=SHEET, events=None):
    require_approval(
        read_events(run.ledger) if events is None else events,
        sheet,
        run.checks,
        key_path=run.investor_key,
        rules_path=run.rules,
    )


def test_the_coverage_is_printed_above_the_term_sheet_with_uncovered_rules_first(project):
    _, said = approve(project)
    text = "\n".join(said)
    assert text.index("SPEC COVERAGE") < text.index("TERM SHEET")
    assert text.index("UNCOVERED (no check cites these") < text.index("COVERED, ANCHORS PRESENT")
    assert "R04 [behaviour] Case is kept." in text.split("TERM SHEET")[0]
    assert "rules 3 | UNCOVERED 1 | anchored 1 | unanchored 1" in text


def test_an_approval_binds_the_rule_list_and_records_a_signed_coverage_summary(project):
    approved, _ = approve(project)
    [event] = read_events(project.ledger)
    assert set(event.data["hashes"]) == {"term_sheet", "test_c01.py", "test_c02.py", "rules.json"}
    assert event.data["hashes"] == content_hashes(approved, project.checks, project.rules)
    summary = event.data["spec"]
    assert summary["uncovered"] == ["R04"] and summary["rules"] == 3
    assert summary["rules_sha256"] == spec.rules_digest(spec.split(IDEA))
    assert summary["anchored"] == 1 and summary["unanchored"] == 1
    check(project, approved)


def test_a_rule_dropped_from_the_stored_list_after_approval_voids_the_approval(project):
    approve(project)
    data = json.loads(project.rules.read_text())
    data["rules"] = data["rules"][:-1]
    project.rules.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(NotApprovedError, match="not the rule list"):
        check(project)


def test_a_harmless_edit_of_the_rule_file_still_voids_it_because_the_bytes_are_hashed(project):
    approve(project)
    project.rules.write_text(project.rules.read_text() + "\n", encoding="utf-8")
    with pytest.raises(NotApprovedError, match="no matching investor approval"):
        check(project)


def test_deleting_the_rule_list_after_approval_voids_it_and_adding_one_later_does_too(
    project, tmp_path
):
    approve(project)
    project.rules.unlink()
    with pytest.raises(NotApprovedError, match="no matching investor approval"):
        check(project)
    plain = RunPaths(tmp_path / "other" / ".boss" / "runs" / "r1")
    plain.checks.mkdir(parents=True)
    (plain.checks / "test_c01.py").write_text(EMPTY)
    (plain.checks / "test_c02.py").write_text(TYPE_OK)
    with plain.writer() as ledger:
        review_term_sheet(
            SHEET, plain.checks, plain.root, ledger, "r1", ask=lambda _: "a", say=lambda _: None
        )
    check(plain)  # an approval made without a rule list is still good without one
    plain.rules.write_text(spec.dumps(spec.split(IDEA)), encoding="utf-8")
    with pytest.raises(NotApprovedError):
        check(plain)


def test_a_forged_coverage_summary_does_not_pass_the_signature(project):
    approve(project)
    [event] = read_events(project.ledger)
    forged_spec = dict(event.data["spec"], uncovered=[])
    forged = Event(
        run="r1",
        round=0,
        actor="investor",
        event=EventType.APPROVED,
        data={"hashes": event.data["hashes"], "spec": forged_spec},
    )
    project.ledger.unlink()
    with LedgerWriter(project.ledger, None) as ledger:  # a worker has no key
        ledger.append(forged)
    with pytest.raises(NotApprovedError):
        check(project)


def test_a_rule_list_that_is_not_the_ideas_cannot_be_approved_only_rejected(project):
    data = json.loads(project.rules.read_text())
    data["rules"] = data["rules"][:-1]
    project.rules.write_text(json.dumps(data), encoding="utf-8")
    result, said = approve(project, answers=("a", "r"))
    assert result is None
    text = "\n".join(said)
    assert "The rule list cannot be used" in text and "Not approved: the rule list is not" in text
    reason = text.split("cannot be used: ", 1)[1].splitlines()[0]
    assert f"the rule list is not the idea's ({reason})" in text
    assert [e.event for e in read_events(project.ledger)] == [EventType.STOPPED]


def test_the_view_is_recomputed_when_the_investor_edits_a_check_and_must_be_seen_again(project):
    def weaken():
        (project.checks / "test_c02.py").write_text(TYPE_BAD)

    result, said = approve(project, answers=("e", "", "a", "a"), edits={1: weaken})
    assert result is not None
    text = "\n".join(said)
    assert "no TypeError" in text, "the edited check lost the exception its rule names"
    assert "CLAIMED, BUT THE CHECK CANNOT BE TESTING IT" in text
    [event] = read_events(project.ledger)
    assert event.data["spec"]["anchor_missing"] == 1


def test_a_check_edited_between_the_view_and_the_yes_is_not_approved(project):
    def sneak():
        (project.checks / "test_c02.py").write_text(TYPE_BAD)

    result, said = approve(project, answers=("a", "a"), edits={0: sneak})
    assert "The term sheet or a check changed since it was shown; review it again." in said
    assert result is not None
    [event] = read_events(project.ledger)
    assert event.data["spec"]["anchor_missing"] == 1, "what was approved is what was shown last"


def test_a_citation_of_a_rule_that_does_not_exist_cannot_be_approved(project):
    bad = dataclasses.replace(
        SHEET, checks=(CheckSpec("c01", "empty", "test_c01.py", "t1", ("R77",)), SHEET.checks[1])
    )
    result, said = approve(project, sheet=bad, answers=("a", "r"))
    assert result is None
    assert any("citations are malformed" in line and "R77" in line for line in said)


def test_the_boss_waivers_are_shown_labelled_and_recorded_with_their_reasons(project):
    result, said = approve(project, untested={"R04": "a note\non style\x1b[31m"})
    assert result is not None
    text = "\n".join(said)
    assert "WAIVED BY THE BOSS (model text, not verified)" in text
    assert "(boss, unverified: a note on style\\x1b[31m)" in text
    [event] = read_events(project.ledger)
    assert event.data["spec"]["waived"] == ["R04"]
    assert "\x1b" not in event.data["spec"]["waived_reasons"]["R04"]


def test_a_run_without_rules_is_approved_exactly_as_before(tmp_path):
    run = RunPaths(tmp_path / "project" / ".boss" / "runs" / "r1")
    run.checks.mkdir(parents=True)
    (run.checks / "test_c01.py").write_text(EMPTY)
    (run.checks / "test_c02.py").write_text(TYPE_OK)
    plain = dataclasses.replace(
        SHEET, checks=tuple(dataclasses.replace(c, criteria=()) for c in SHEET.checks)
    )
    with run.writer() as ledger:
        approved = review_term_sheet(
            plain, run.checks, run.root, ledger, "r1", ask=lambda _: "a", say=lambda _: None
        )
    [event] = read_events(run.ledger)
    assert set(event.data) - {"sig"} == {"hashes"} and "rules.json" not in event.data["hashes"]
    require_approval(read_events(run.ledger), approved, run.checks, key_path=run.investor_key)
