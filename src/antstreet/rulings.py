"""The investor's rulings on what a worker could not settle: a disputed check, a blocked task.

The worker and the rule never decide these. A ruling is an `investor` event in the ledger; the
term sheet and its approval are untouched, so a dropped check is dropped by the investor's own
recorded decision, not by editing what was approved.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from antstreet.ledger import Event, EventType
from antstreet.redact import safe_text

DROPPED, KEPT, UNBLOCKED, DECLINED = "dropped", "kept", "unblocked", "declined"
MAX_NOTE_CHARS = 1_000
# The `stopped` reason of a run that met a dispute with nobody at a terminal to rule on it.
RULING_AWAITED = "awaiting the investor's ruling on a dispute"

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


def awaited(events: Sequence[Event]) -> list[dict[str, str]]:
    """The disputes the run stopped on since it was last resumed, less those already ruled: each
    {task, check, worker}. Parallel tasks can each stop on theirs in one wave, so every such stop
    since the resume counts."""
    pending: list[object] = []
    for e in events:
        if e.event is EventType.STOPPED and e.actor == "boss":
            if e.data.get("reason") == RULING_AWAITED:
                pending += list(e.data.get("disputes") or ())
        elif e.event is EventType.RESUMED and e.actor == "investor":
            pending = []
    settled = ruled(events, KEPT) | ruled(events, DROPPED)
    return [
        {k: str(d.get(k, "")) for k in ("task", "check", "worker")}
        for d in pending
        if isinstance(d, dict) and d.get("check") and d["check"] not in settled
    ]


def how_to_rule(run: str, disputes: Sequence[Mapping[str, str]]) -> str:
    """The commands only the investor runs to rule on each waiting dispute, then to go on."""
    lines = [f"\nRun {run} is {RULING_AWAITED}. To rule, run this yourself, one line per check:"]
    for d in disputes:
        check = d["check"]
        lines.append(f"  boss approve {run} --dispute {check} --ruling drop   (drop {check})")
        lines.append(f"  boss approve {run} --dispute {check} --ruling keep   (it must pass)")
    lines.append(
        "In Claude Code, type it with the `!` prefix: the ruling is yours, never the agent's. "
        f"Then continue with `boss resume {run}`."
    )
    return "\n".join(lines)


def notes_since(
    events: Sequence[Event], task: str, since: int, worker: str | None = None
) -> list[str]:
    """What the investor ruled on this task after event index `since`, as lines for the next
    brief of `worker`. A ruling on a dispute or block that another worker raised is worded as
    the predecessor's, with its reason for a dispute: the reader never made that claim."""
    reasons = {
        str(e.data["check"]): str(e.data.get("reason", ""))
        for e in events
        if e.event is EventType.DISPUTED and e.data.get("task") == task and "check" in e.data
    }
    notes = []
    for e in events[since:]:
        if not _is_ruling(e) or e.data.get("task") != task:
            continue
        ruling, check = e.data.get("ruling"), e.data.get("check")
        theirs = worker is not None and e.data.get("worker") not in (None, worker)
        if ruling == KEPT and theirs:
            reason = safe_text(reasons.get(str(check), ""), limit=300)
            notes.append(
                "The investor ruled on the dispute your predecessor raised "
                f'(its reason: "{reason}"): check {check} stands. Make it pass.'
            )
        elif ruling == KEPT:
            notes.append(f"The investor ruled on your dispute: check {check} stands. Make it pass.")
        elif ruling == DROPPED:
            notes.append(f"The investor dropped check {check}. It is no longer required.")
        elif ruling == UNBLOCKED:
            who = "your predecessor's block" if theirs else "your block"
            notes.append(f"The investor answered {who}: {e.data.get('note', '')}")
    return notes


def _is_ruling(event: Event) -> bool:
    return event.event is EventType.RULED and event.actor == "investor"
