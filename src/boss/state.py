"""Run state rebuilt from ledger events. The ledger is the only source of truth, so the live
loop, offline replay and resume all read a run the same way.

Ledger data contract for stage 2 (keys inside each event's `data`):

    hired        boss        {worker, task, session, model}
    slice_start  worker:<w>  {slice, task, cap_micros}
    slice_end    worker:<w>  {slice, task, outcome, status, session_total_micros, ...}
                             with the event's cost_micros = this slice's own spend
    check_result gate        {check, task, status, detail, worker, slice}
    fired        rule        {worker, task, reason, evidence}
    reassigned   boss        {task, from, to}
    blocked      worker:<w>  {task, reason}
    round_closed boss        {passed, total, unlocked}
"""

from __future__ import annotations

from collections.abc import Sequence

from boss.errors import Outcome
from boss.ledger import Event, EventType
from boss.rule import SliceRecord


def worker_name(actor: str) -> str | None:
    return actor.removeprefix("worker:") if actor.startswith("worker:") else None


def slice_history(events: Sequence[Event]) -> dict[str, list[SliceRecord]]:
    """Per worker, its finished slices in order, each with the checks passing after it."""
    passing: dict[tuple[str, int], set[str]] = {}
    for e in events:
        if e.event is EventType.CHECK_RESULT and "worker" in e.data and "slice" in e.data:
            key = (str(e.data["worker"]), int(e.data["slice"]))
            passing.setdefault(key, set())
            if e.data.get("status") == "passed":
                passing[key].add(str(e.data["check"]))

    history: dict[str, list[SliceRecord]] = {}
    for e in events:
        worker = worker_name(e.actor)
        if e.event is not EventType.SLICE_END or worker is None:
            continue
        number = int(e.data.get("slice", len(history.get(worker, [])) + 1))
        status = (e.data.get("status") or {}).get("status", "none")
        history.setdefault(worker, []).append(
            SliceRecord(
                slice=number,
                cost_micros=e.cost_micros,
                outcome=Outcome(e.data.get("outcome", Outcome.CRASHED)),
                status=str(status),
                passing=frozenset(passing.get((worker, number), set())),
            )
        )
    return history


def worker_tasks(events: Sequence[Event]) -> dict[str, str]:
    """Which task each hired worker was given."""
    return {
        str(e.data["worker"]): str(e.data.get("task", ""))
        for e in events
        if e.event is EventType.HIRED and "worker" in e.data
    }


def fired_workers(events: Sequence[Event]) -> set[str]:
    return {str(e.data["worker"]) for e in events if e.event is EventType.FIRED}
