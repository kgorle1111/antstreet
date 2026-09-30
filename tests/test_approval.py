import json

import pytest

from boss.approval import (
    NotApprovedError,
    content_hashes,
    render,
    require_approval,
    review_term_sheet,
)
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.termsheet import CheckSpec, Round, Task, TermSheet

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
C02 = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
SHEET = TermSheet(
    idea="Reverse a string.",
    budget_micros=500_000,
    rounds=(Round(1, 500_000, 2),),
    checks=(
        CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),
        CheckSpec("c02", "empty string", "test_c02.py", "t1"),
    ),
    tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
)


@pytest.fixture
def run(tmp_path):
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(C01)
    (checks / "test_c02.py").write_text(C02)
    ledger_path = tmp_path / "ledger.jsonl"

    def review(answers, edits=None):
        """answers: replies in order. edits: {reply_index: callable} run just before that reply."""
        said, calls = [], []

        def ask(prompt):
            said.append(prompt)
            index = len(calls)
            calls.append(prompt)
            if edits and index in edits:
                edits[index]()
            return answers[index]

        with LedgerWriter(ledger_path) as ledger:
            result = review_term_sheet(
                SHEET, checks, tmp_path, ledger, "r1", ask=ask, say=said.append
            )
        return result, said

    review.checks = checks
    review.dir = tmp_path
    review.events = lambda: read_events(ledger_path)
    return review


def test_approval_is_recorded_with_content_hashes(run):
    approved, _ = run(["a"])
    assert approved is not None
    assert approved.approved_by_investor
    [event] = run.events()
    assert (event.actor, event.event, event.round) == ("investor", EventType.APPROVED, 0)
    assert event.data["hashes"] == content_hashes(approved, run.checks)
    saved = TermSheet.from_json((run.dir / "term_sheet.json").read_text())
    assert saved.approved_by_investor
    require_approval(run.events(), approved, run.checks)


def test_rejection_is_recorded_and_blocks_spending(run):
    result, said = run(["r"])
    assert result is None
    [event] = run.events()
    assert event.event is EventType.STOPPED
    assert "Rejected. Nothing was funded." in said
    with pytest.raises(NotApprovedError):
        require_approval(run.events(), SHEET, run.checks)


def test_end_of_input_counts_as_rejection(run):
    def ask(_):
        raise EOFError

    with LedgerWriter(run.dir / "ledger.jsonl") as ledger:
        assert (
            review_term_sheet(SHEET, run.checks, run.dir, ledger, "r1", ask=ask, say=lambda _: None)
            is None
        )
    assert run.events()[0].event is EventType.STOPPED


def test_unrecognised_answer_asks_again(run):
    approved, said = run(["maybe", "a"])
    assert approved is not None
    assert "Unrecognised answer 'maybe'." in said


def test_edit_that_breaks_validation_is_refused_until_fixed(run):
    def break_check():
        (run.checks / "test_c02.py").write_text("def test_x():\n    pass\n")

    def fix_check():
        (run.checks / "test_c02.py").write_text(C02.replace("''", "str()"))

    approved, said = run(["e", "", "", "a"], edits={1: break_check, 2: fix_check})
    assert any("check c02 passes on an empty workspace" in s for s in said if s)
    assert approved is not None
    require_approval(run.events(), approved, run.checks)


def test_edited_budget_in_json_is_picked_up_and_revalidated(run):
    def raise_budget():
        path = run.dir / "term_sheet.json"
        raw = json.loads(path.read_text())
        raw["budget_micros"] = raw["rounds"][0]["budget_micros"] = 900_000
        raw["approved_by_investor"] = True  # an edit cannot pre-approve
        path.write_text(json.dumps(raw))

    approved, said = run(["e", "", "a"], edits={1: raise_budget})
    assert approved.budget_micros == 900_000
    assert "Budget: $0.9 (estimated cost, not a bill)" in said[-2]


def test_changing_a_check_after_approval_voids_it(run):
    approved, _ = run(["a"])
    (run.checks / "test_c01.py").write_text(C01.replace("'ba'", "'ab'"))
    with pytest.raises(NotApprovedError):
        require_approval(run.events(), approved, run.checks)


def test_only_the_investor_can_approve(run):
    forged = Event(
        run="r1",
        round=0,
        actor="boss",
        event=EventType.APPROVED,
        data={"hashes": content_hashes(SHEET, run.checks)},
    )
    with pytest.raises(NotApprovedError):
        require_approval([forged], SHEET, run.checks)


def test_render_shows_the_brief_and_every_check_in_full(run):
    text = render(SHEET, run.checks)
    assert "Create rev.py with reverse(s)." in text
    assert C01.rstrip() in text and C02.rstrip() in text
    assert "Round 1: $0.5, next unlocks at 2 passing checks" in text


def test_advisory_notes_are_shown_under_the_sheet_and_change_nothing_that_is_approved(tmp_path):
    from boss.approval import content_hashes, review_term_sheet
    from boss.ledger import LedgerWriter, read_events

    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(C01)
    (checks / "test_c02.py").write_text(C02)
    said = []
    with LedgerWriter(tmp_path / "ledger.jsonl") as ledger:
        plain = review_term_sheet(
            SHEET, checks, tmp_path, ledger, "r1", ask=lambda q: "a", say=said.append
        )
        noted = review_term_sheet(
            SHEET,
            checks,
            tmp_path,
            ledger,
            "r1",
            ask=lambda q: "a",
            say=said.append,
            notes=["auditor's opinion, unverified: c02 is unsupported", "coverage: S1.1 -> c01"],
        )
    assert said[-2:] == [
        "auditor's opinion, unverified: c02 is unsupported",
        "coverage: S1.1 -> c01",
    ]
    assert said[0] == said[1]  # the sheet itself is rendered the same with or without notes
    first, second = read_events(tmp_path / "ledger.jsonl")
    assert first.data == second.data == {"hashes": content_hashes(plain, checks)}
    assert noted == plain
