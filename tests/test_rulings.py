"""The investor's rulings: how an answer is read, and what the ledger's rulings mean."""

import pytest

from boss.ledger import Event, EventType
from boss.rulings import (
    DROPPED,
    KEPT,
    MAX_NOTE_CHARS,
    UNBLOCKED,
    ask_block,
    ask_dispute,
    notes_since,
    ruled,
)


def answers(*replies):
    queue, asked = list(replies), []

    def ask(question):
        asked.append(question)
        if not queue:
            raise EOFError
        return queue.pop(0)

    ask.asked = asked
    return ask


def dispute(ask):
    return ask_dispute(ask, task="t1", worker="w1", check="c05", description="d", reason="r")


def ruling(kind, *, actor="investor", task="t1", check="c05", **extra) -> Event:
    data = {"task": task, "worker": "w1", "ruling": kind} | extra
    if check is not None:
        data["check"] = check
    return Event(run="r", round=1, actor=actor, event=EventType.RULED, data=data)


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("d", DROPPED), ("D", DROPPED), (" drop ", DROPPED), ("k", KEPT), ("Keep", KEPT)],
)
def test_a_clear_answer_to_a_dispute_is_a_ruling(answer, expected):
    assert dispute(answers(answer)) == expected


@pytest.mark.parametrize("answer", ["", "s", "a", "y", "yes", "dk", "drop it", "keep?", "0"])
def test_any_other_answer_to_a_dispute_sets_the_task_aside(answer):
    assert dispute(answers(answer)) is None


def test_nobody_at_the_keyboard_sets_the_task_aside():
    assert dispute(answers()) is None
    assert ask_block(answers(), task="t1", worker="w1", reason="r") is None
    assert ask_block(answers("u"), task="t1", worker="w1", reason="r") is None  # no note came


def test_an_interrupt_is_not_read_as_an_answer():
    def interrupted(question):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        dispute(interrupted)


def test_the_dispute_question_shows_the_check_its_description_and_the_workers_reason():
    ask = answers("s")
    ask_dispute(ask, task="t9", worker="w3", check="c02", description="empty input", reason="why")
    [question] = ask.asked
    assert question.startswith('Task t9: w3 disputes check c02 (empty input): "why"')
    assert "[d]rop the check / [k]eep it" in question


def test_an_unblocking_note_is_one_bounded_line_made_safe_to_store():
    ask = answers("u", "  use  slicing\n\x1b[31m not a loop ")
    assert ask_block(ask, task="t1", worker="w1", reason="r") == "use slicing \\x1b[31m not a loop"
    long = ask_block(answers("unblock", "x" * 5_000), task="t1", worker="w1", reason="r")
    assert len(long) == MAX_NOTE_CHARS and long.endswith(" [cut]")


@pytest.mark.parametrize("first", ["s", "a", "", "note without saying u"])
def test_a_block_is_lifted_only_by_saying_so_first(first):
    ask = answers(first, "a note that must not be read")
    assert ask_block(ask, task="t1", worker="w1", reason="r") is None
    assert len(ask.asked) == 1


def test_ruled_lists_checks_by_ruling_and_ignores_anyone_but_the_investor():
    events = [
        ruling(DROPPED, check="c01"),
        ruling(KEPT, check="c02"),
        ruling(DROPPED, check="c03", actor="worker:w1"),
        ruling(DROPPED, check="c04", actor="boss"),
        ruling(UNBLOCKED, check=None, note="n"),
        Event(run="r", round=1, actor="investor", event=EventType.APPROVED, data={"check": "c9"}),
    ]
    assert ruled(events, DROPPED) == {"c01"}
    assert ruled(events, KEPT) == {"c02"}
    assert ruled(events, UNBLOCKED) == frozenset()
    assert ruled([], DROPPED) == frozenset()


def test_notes_for_the_worker_cover_only_its_task_after_its_last_slice_and_only_the_investor():
    events = [
        ruling(KEPT, check="c01"),  # index 0: before `since`
        ruling(KEPT, check="c02"),
        ruling(DROPPED, check="c03"),
        ruling(UNBLOCKED, check=None, note="use slicing"),
        ruling(KEPT, check="c04", task="t2"),
        ruling(KEPT, check="c05", actor="worker:w1"),
    ]
    assert notes_since(events, "t1", 1) == [
        "The investor ruled on your dispute: check c02 stands. Make it pass.",
        "The investor dropped check c03. It is no longer required.",
        "The investor answered your block: use slicing",
    ]
    assert notes_since(events, "t1", len(events)) == []


def test_a_ruling_on_a_dispute_another_worker_raised_is_worded_as_its_predecessors():
    raised = Event(
        run="r",
        round=1,
        actor="worker:w1",
        event=EventType.DISPUTED,
        data={"task": "t1", "worker": "w1", "check": "c05", "reason": "the idea says otherwise"},
    )
    events = [
        raised,
        ruling(KEPT, check="c05"),
        ruling(UNBLOCKED, check=None, note="use slicing"),
        ruling(DROPPED, check="c06"),
    ]
    assert notes_since(events, "t1", 0, "w2") == [
        "The investor ruled on the dispute your predecessor raised "
        '(its reason: "the idea says otherwise"): check c05 stands. Make it pass.',
        "The investor answered your predecessor's block: use slicing",
        "The investor dropped check c06. It is no longer required.",
    ]
    assert notes_since(events, "t1", 0, "w1")[0].startswith("The investor ruled on your dispute")
    assert notes_since(events, "t1", 0)[1] == "The investor answered your block: use slicing"
