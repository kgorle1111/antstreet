"""The investor's rulings on what a worker could not settle: a disputed check, a blocked task.

The worker and the rule never decide these. A ruling is an `investor` event in the ledger; the
term sheet and its approval are untouched, so a dropped check is dropped by the investor's own
recorded decision, not by editing what was approved.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from boss.ledger import Event, EventType
from boss.redact import safe_text

DROPPED, KEPT, UNBLOCKED, DECLINED = "dropped", "kept", "unblocked", "declined"
MAX_NOTE_CHARS = 1_000

Ask = Callable[[str], str]


def _answer(ask: Ask, question: str) -> str:
    try:
        return ask(question).strip()
    except EOFError:  # nobody is there to rule: the task is set aside
        return ""


def ask_dispute(
    ask: Ask, *, task: str, worker: str, check: str, description: str, reason: str
) -> str | None:
    """DROPPED, KEPT, or None to set the task aside. Anything but a clear answer sets it aside."""
    answer = _answer(
        ask,
        f'Task {task}: {worker} disputes check {check} ({description}): "{reason}"\n'
        "[d]rop the check / [k]eep it (the worker must satisfy it) / [s]et the task aside ",
    ).lower()
    if answer in ("d", "drop"):
        return DROPPED
    if answer in ("k", "keep"):
        return KEPT
    return None


def ask_block(ask: Ask, *, task: str, worker: str, reason: str) -> str | None:
    """The investor's note that unblocks the worker, or None to set the task aside."""
    answer = _answer(
        ask,
        f'Task {task}: {worker} says it cannot go on: "{reason}"\n'
        "[u]nblock it with a note / [s]et the task aside ",
    ).lower()
    if answer not in ("u", "unblock"):
        return None
    note = " ".join(_answer(ask, "Your note to the worker: ").split())
    return safe_text(note, limit=MAX_NOTE_CHARS) or None


def ruled(events: Sequence[Event], ruling: str) -> frozenset[str]:
    """Checks the investor has given this ruling on."""
    return frozenset(
        str(e.data["check"])
        for e in events
        if _is_ruling(e) and e.data.get("ruling") == ruling and "check" in e.data
    )


def notes_since(events: Sequence[Event], task: str, since: int) -> list[str]:
    """What the investor ruled on this task after event index `since`, as lines for the worker's
    next brief."""
    notes = []
    for e in events[since:]:
        if not _is_ruling(e) or e.data.get("task") != task:
            continue
        ruling, check = e.data.get("ruling"), e.data.get("check")
        if ruling == KEPT:
            notes.append(f"The investor ruled on your dispute: check {check} stands. Make it pass.")
        elif ruling == DROPPED:
            notes.append(f"The investor dropped check {check}. It is no longer required.")
        elif ruling == UNBLOCKED:
            notes.append(f"The investor answered your block: {e.data.get('note', '')}")
    return notes


def _is_ruling(event: Event) -> bool:
    return event.event is EventType.RULED and event.actor == "investor"
