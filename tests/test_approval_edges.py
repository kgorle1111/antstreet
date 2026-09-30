"""Approval edge cases: end-of-input mid-edit, hostile edits, stale approvals and hash inputs."""

import dataclasses
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
def checks(tmp_path):
    path = tmp_path / "checks"
    path.mkdir()
    (path / "test_c01.py").write_text(C01)
    (path / "test_c02.py").write_text(C02)
    return path


class Session:
    """Drives review_term_sheet with scripted replies; an exception in the script is raised."""

    def __init__(self, tmp_path, checks):
        self.dir, self.checks = tmp_path, checks
        self.ledger_path = tmp_path / "ledger.jsonl"
        self.said: list[str] = []
        self.prompts: list[str] = []

    def review(self, replies):
        script = iter(replies)

        def ask(prompt):
            self.prompts.append(prompt)
            reply = next(script)
            if callable(reply):
                reply = reply()
            if isinstance(reply, BaseException):
                raise reply
            return reply

        with LedgerWriter(self.ledger_path) as ledger:
            return review_term_sheet(
                SHEET, self.checks, self.dir, ledger, "r1", ask=ask, say=self.said.append
            )

    def events(self):
        return read_events(self.ledger_path)

    @property
    def sheet_file(self):
        return self.dir / "term_sheet.json"


@pytest.fixture
def session(tmp_path, checks):
    return Session(tmp_path, checks)


@pytest.mark.parametrize("answer", ["a", "A", "  approve  ", "APPROVE", "Approve\n"])
def test_approve_is_case_and_whitespace_insensitive(session, answer):
    assert session.review([answer]) is not None
    assert [e.event for e in session.events()] == [EventType.APPROVED]


@pytest.mark.parametrize("answer", ["r", "R", " reject ", "REJECT"])
def test_reject_is_case_and_whitespace_insensitive(session, answer):
    assert session.review([answer]) is None
    assert [e.event for e in session.events()] == [EventType.STOPPED]


def test_keyboard_interrupt_at_the_prompt_is_a_recorded_rejection(session):
    assert session.review([KeyboardInterrupt()]) is None
    [event] = session.events()
    assert event.event is EventType.STOPPED
    assert event.data == {"reason": "term sheet rejected"}
    assert "Rejected. Nothing was funded." in session.said


def test_end_of_input_while_waiting_for_an_edit_keeps_the_sheet_and_asks_again(session):
    approved = session.review(["edit", EOFError(), "approve"])
    assert approved == dataclasses.replace(SHEET, approved_by_investor=True)
    assert any(s.startswith("Edit ") for s in session.said)
    assert [e.event for e in session.events()] == [EventType.APPROVED]


def test_end_of_input_after_an_edit_ends_in_rejection_not_a_hang(session):
    assert session.review(["e", EOFError(), EOFError()]) is None
    assert [e.event for e in session.events()] == [EventType.STOPPED]


def test_end_of_input_while_fixing_an_invalid_edit_returns_to_the_menu(session, checks):
    def break_check():
        (checks / "test_c02.py").write_text("def test_x():\n    pass\n")
        return ""

    assert session.review(["e", break_check, EOFError(), "r"]) is None
    reported = next(s for s in session.said if "does not validate" in s)
    assert "check c02 passes on an empty workspace" in reported
    assert sum(s.startswith("TERM SHEET") for s in session.said) == 2
    assert [e.event for e in session.events()] == [EventType.STOPPED]


def test_a_check_broken_since_the_last_validation_cannot_be_approved(session, checks):
    def break_then_approve():
        (checks / "test_c02.py").write_text("def test_x():\n    pass\n")
        return "a"

    assert session.review([break_then_approve, "r"]) is None
    assert any("check c02 passes on an empty workspace" in s for s in session.said)
    assert [e.event for e in session.events()] == [EventType.STOPPED]


def test_a_file_edited_since_it_was_shown_is_shown_again_and_approved_as_it_is_on_disk(session):
    def edit_idea():
        raw = json.loads(session.sheet_file.read_text())
        raw["idea"] = "Reverse any string."
        session.sheet_file.write_text(json.dumps(raw))
        return "a"

    approved = session.review([edit_idea, "a"])
    assert approved.idea == "Reverse any string."
    assert sum(s.startswith("TERM SHEET") for s in session.said) == 2
    assert TermSheet.from_json(session.sheet_file.read_text()) == approved


def test_edit_that_leaves_invalid_json_is_reported_then_recovered(session):
    original = {}

    def corrupt():
        original["text"] = session.sheet_file.read_text()
        session.sheet_file.write_text("{ not json")
        return ""

    def restore():
        session.sheet_file.write_text(original["text"])
        return ""

    approved = session.review(["e", corrupt, restore, "a"])
    assert approved is not None
    problem = next(s for s in session.said if "does not validate" in s)
    assert "not a valid term sheet" in problem
    assert session.prompts.count("Fix the files, then press Enter to re-check. ") == 1


def test_edit_with_wrong_typed_json_field_is_reported_not_raised(session):
    def corrupt():
        raw = json.loads(session.sheet_file.read_text())
        raw["budget_micros"] = "lots"
        session.sheet_file.write_text(json.dumps(raw))
        return ""

    def restore():
        session.sheet_file.write_text(SHEET.to_json())
        return ""

    assert session.review(["e", corrupt, restore, "a"]) is not None
    assert any("budget_micros must be" in s for s in session.said)


@pytest.mark.xfail(
    strict=True,
    reason="approval.py:_reload_after_edit only catches TermSheetError; a term_sheet.json that "
    "is missing when the investor presses Enter raises FileNotFoundError and aborts the review",
)
def test_deleted_term_sheet_file_during_an_edit_is_reported_not_raised(session):
    def delete():
        session.sheet_file.unlink()
        return ""

    def restore():
        session.sheet_file.write_text(SHEET.to_json())
        return ""

    assert session.review(["e", delete, restore, "a"]) is not None


@pytest.mark.xfail(
    strict=True,
    reason="approval.py:review_term_sheet: an investor edit that sets approved_by_investor stays "
    "in term_sheet.json after a rejection, although only code is meant to set it",
)
def test_a_rejected_sheet_never_says_approved_on_disk(session):
    def preapprove():
        raw = json.loads(session.sheet_file.read_text())
        raw["approved_by_investor"] = True
        session.sheet_file.write_text(json.dumps(raw))
        return ""

    assert session.review(["e", preapprove, "r"]) is None
    assert TermSheet.from_json(session.sheet_file.read_text()).approved_by_investor is False


def test_approval_rewrites_the_sheet_file_with_the_flag_set_and_nothing_else_changed(session):
    session.review(["a"])
    saved = TermSheet.from_json(session.sheet_file.read_text())
    assert saved == dataclasses.replace(SHEET, approved_by_investor=True)


def test_review_overwrites_a_preapproved_sheet_file_before_asking(session):
    session.sheet_file.write_text(dataclasses.replace(SHEET, approved_by_investor=True).to_json())
    seen = {}

    def peek():
        seen["flag"] = TermSheet.from_json(session.sheet_file.read_text()).approved_by_investor
        return "r"

    session.review([peek])
    assert seen == {"flag": False}


def test_unrecognised_answers_never_reach_the_ledger(session):
    session.review(["", "yes", "approve please", "r"])
    assert [e.event for e in session.events()] == [EventType.STOPPED]
    assert "Unrecognised answer ''." in session.said
    assert "Unrecognised answer 'yes'." in session.said


def test_the_menu_is_shown_again_after_every_unrecognised_answer(session):
    session.review(["?", "??", "r"])
    assert sum(s.startswith("TERM SHEET") for s in session.said) == 3


# --- require_approval and content_hashes ---------------------------------------------------


def approval(sheet, checks, actor="investor", run="r1"):
    return Event(
        run=run,
        round=0,
        actor=actor,
        event=EventType.APPROVED,
        data={"hashes": content_hashes(sheet, checks)},
    )


def test_no_events_means_not_approved(checks):
    with pytest.raises(NotApprovedError, match="no matching investor approval"):
        require_approval([], SHEET, checks)


def test_a_stale_approval_is_ignored_but_a_later_matching_one_counts(checks):
    stale = approval(SHEET, checks)
    (checks / "test_c01.py").write_text(C01 + "\n# edited\n")
    with pytest.raises(NotApprovedError):
        require_approval([stale], SHEET, checks)
    fresh = approval(SHEET, checks)
    require_approval([stale, fresh], SHEET, checks)
    require_approval(iter([stale, fresh]), SHEET, checks)


def test_other_event_types_from_the_investor_do_not_count_as_approval(checks):
    denial = Event(
        run="r1",
        round=0,
        actor="investor",
        event=EventType.STOPPED,
        data={"hashes": content_hashes(SHEET, checks)},
    )
    with pytest.raises(NotApprovedError):
        require_approval([denial], SHEET, checks)


def test_an_approval_with_a_missing_or_partial_hash_map_does_not_count(checks):
    hashes = content_hashes(SHEET, checks)
    for data in ({}, {"hashes": {"term_sheet": hashes["term_sheet"]}}, {"hashes": None}):
        event = Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        with pytest.raises(NotApprovedError):
            require_approval([event], SHEET, checks)


def test_approval_carrying_an_extra_hash_entry_does_not_count(checks):
    hashes = content_hashes(SHEET, checks) | {"extra.py": "0" * 64}
    event = Event(
        run="r1", round=0, actor="investor", event=EventType.APPROVED, data={"hashes": hashes}
    )
    with pytest.raises(NotApprovedError):
        require_approval([event], SHEET, checks)


@pytest.mark.parametrize(
    "change",
    [
        {"idea": "Reverse a string!"},
        {"budget_micros": 500_001},
        {"rounds": (Round(1, 500_000, 1),)},
        {"tasks": (Task("t1", "Create rev.py with reverse(s).", ("rev.py", "x.py")),)},
        {"checks": (SHEET.checks[0], dataclasses.replace(SHEET.checks[1], description="other"))},
    ],
    ids=["idea", "budget", "unlock", "paths", "check-description"],
)
def test_any_change_to_the_term_sheet_voids_the_approval(checks, change):
    approved = approval(SHEET, checks)
    with pytest.raises(NotApprovedError):
        require_approval([approved], dataclasses.replace(SHEET, **change), checks)


def test_the_approval_flag_itself_does_not_change_the_hashes(checks):
    flagged = dataclasses.replace(SHEET, approved_by_investor=True)
    assert content_hashes(flagged, checks) == content_hashes(SHEET, checks)


def test_a_single_byte_change_in_a_check_changes_only_that_checks_hash(checks):
    before = content_hashes(SHEET, checks)
    (checks / "test_c02.py").write_bytes((checks / "test_c02.py").read_bytes() + b" ")
    after = content_hashes(SHEET, checks)
    assert after["term_sheet"] == before["term_sheet"]
    assert after["test_c01.py"] == before["test_c01.py"]
    assert after["test_c02.py"] != before["test_c02.py"]


def test_a_deleted_check_file_surfaces_as_an_os_error_not_as_a_silent_pass(checks):
    approved = approval(SHEET, checks)
    (checks / "test_c01.py").unlink()
    with pytest.raises(FileNotFoundError):
        require_approval([approved], SHEET, checks)


def test_render_lists_every_round_task_and_check_in_order(checks):
    sheet = dataclasses.replace(
        SHEET,
        budget_micros=1_500_000,
        rounds=(Round(1, 500_000, 1), Round(2, 1_000_000, 2)),
        tasks=(
            Task("t1", "Build rev.py.", ("rev.py", "pkg")),
            Task("t2", "Build docs.", (".",)),
        ),
    )
    assert render(sheet, checks) == (
        "TERM SHEET\n"
        "Idea: Reverse a string.\n"
        "Budget: $1.5 (estimated cost, not a bill)\n"
        "Round 1: $0.5, next unlocks at 1 passing checks\n"
        "Round 2: $1, next unlocks at 2 passing checks\n"
        "\n"
        "Task t1 (owns rev.py, pkg):\n"
        "  Build rev.py.\n"
        "\n"
        "Task t2 (owns .):\n"
        "  Build docs.\n"
        "\n"
        "Check c01 [t1] reverses a word\n"
        f"--- {checks / 'test_c01.py'}\n"
        f"{C01.rstrip()}\n"
        "\n"
        "Check c02 [t1] empty string\n"
        f"--- {checks / 'test_c02.py'}\n"
        f"{C02.rstrip()}"
    )


def test_render_survives_a_check_that_is_not_utf8_and_hides_a_bom(checks):
    (checks / "test_c01.py").write_bytes(b"\xef\xbb\xbfdef test_a():\n    pass\n# caf\xe9\n")
    shown = render(SHEET, checks)
    assert "\ufeff" not in shown
    assert "def test_a():" in shown
