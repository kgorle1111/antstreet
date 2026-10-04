"""KPI figures read from one run's ledger, and nothing else (never from model text).

Shared by `boss report` (one run) and `boss.bench.kpi` (many cells), so a run's figure and the
benchmark's figure for the same run are the same count.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from boss.held_out import SCOPE as HELD_OUT_SCOPE
from boss.ledger import Event, EventType

# `ABANDONED` reasons that follow a question put to the investor (a disputed check, a blocked
# worker, a refusal). Another reason ("already reassigned once") is the boss's own call.
_SET_ASIDE_AFTER_QUESTION = ("disputed", "blocked", "refusal")
_TERM_SHEET_REJECTED = "term sheet rejected"


def _is_question(e: Event) -> bool:
    if e.event is EventType.ABANDONED:
        return e.actor == "boss" and e.data.get("reason") in _SET_ASIDE_AFTER_QUESTION
    if e.actor != "investor":
        return False
    if e.event is EventType.STOPPED:
        reason = e.data.get("reason")
        return isinstance(reason, str) and (
            reason == _TERM_SHEET_REJECTED
            or (reason.startswith("round ") and reason.endswith(" not funded"))
        )
    return e.event in (
        EventType.APPROVED,
        EventType.RULED,
        EventType.RESUMED,
        EventType.TOPPED_UP,
    )


def investor_questions(events: Sequence[Event]) -> int:
    """How many questions the investor had to answer in this run, counted from the ledger.

    One question is one decision the run needed from the investor, and each leaves one event:

    - the term sheet: `approved` (round 0) or `stopped` "term sheet rejected";
    - a round's funding, or the fix round: `approved` with a round, or `stopped` "round N not
      funded";
    - a worker's dispute or block: `ruled` by the investor, or `abandoned` for "disputed",
      "blocked" or "refusal" (the task was set aside, the answer a benchmark's automatic `a`
      gives, so what would have been asked is counted);
    - the fix round the critic proposed, when declined: `ruled` "declined";
    - the investor's own `resumed` and `topped_up`, each a step they had to take to go on.

    Not counted: an edit-and-re-check loop at the term sheet (the ledger records none of it, so
    this is a lower bound), the second prompt of an unblock (the note, one decision), and
    "interrupted before approval" (nothing was answered). A declined fix round is also recorded
    when `--review-cycles 0` offered none, so it can over-count by one there.
    """
    return sum(_is_question(e) for e in events)


def product_verdict(events: Sequence[Event]) -> tuple[int, int] | None:
    """(passed, graded) for the assembled product since the last slice, or None when no slice
    ended or no product result was recorded (nothing built, or a ledger from before the verdict)."""
    last = max((i for i, e in enumerate(events) if e.event is EventType.SLICE_END), default=-1)
    if last < 0:
        return None
    latest: dict[str, bool] = {}
    for e in events[last + 1 :]:
        if (
            e.event is EventType.CHECK_RESULT
            and e.data.get("scope") == "product"
            and "check" in e.data
        ):
            latest[str(e.data["check"])] = e.data.get("status") == "passed"
    return (sum(latest.values()), len(latest)) if latest else None


def built(events: Sequence[Event]) -> bool:
    return any(e.event is EventType.SLICE_END for e in events)


def held_out_graded(events: Sequence[Event]) -> dict[str, bool]:
    """The latest held-out result of each check that has one."""
    graded: dict[str, bool] = {}
    for e in events:
        if (
            e.event is EventType.CHECK_RESULT
            and e.data.get("scope") == HELD_OUT_SCOPE
            and "check" in e.data
        ):
            graded[str(e.data["check"])] = e.data.get("status") == "passed"
    return graded


def single_final_status(events: Sequence[Event]) -> str | None:
    """The status word the single arm's last slice ended with; None when no slice ended or it
    reported none."""
    ends = [e for e in events if e.event is EventType.SLICE_END]
    status = ends[-1].data.get("status") if ends else None
    word = status.get("status") if isinstance(status, dict) else None
    return word if isinstance(word, str) else None


def single_said_done(events: Sequence[Event]) -> bool:
    """The single arm's own claim: its last slice ended with the status word `done`."""
    return single_final_status(events) == "done"


def span_seconds(events: Sequence[Event]) -> float | None:
    """Seconds from the first to the last ledger event: it leaves out the time before the first
    event is written and includes any wait for the investor. None with fewer than two events."""
    if len(events) < 2:
        return None
    stamps = [datetime.fromisoformat(e.ts) for e in events]
    try:
        return (max(stamps) - min(stamps)).total_seconds()
    except TypeError:  # stamps with and without a time zone cannot be compared
        return None
