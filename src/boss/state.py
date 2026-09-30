"""Run state rebuilt from ledger events. The ledger is the only source of truth, so the live
loop, offline replay and resume all read a run the same way.

Ledger data contract for stage 2 (keys inside each event's `data`):

    hired        boss        {worker, task, session, model, prompt}
    slice_start  worker:<w>  {slice, task, cap_micros}
    slice_end    worker:<w>  {slice, task, outcome, status, session_total_micros, ...}
                             with the event's cost_micros = this slice's own spend
    check_result gate        {check, task, status, detail, worker, slice}
    fired        rule        {worker, task, reason, evidence}
    reassigned   boss        {task, from, to}
    blocked      worker:<w>  {task, reason}
    disputed     worker:<w>  {task, check, reason, worker, slice}
    round_closed boss        {passed, total, unlocked}
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from boss.errors import INFRASTRUCTURE, Outcome
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

    disputed: dict[tuple[str, int], set[str]] = {}
    for e in events:
        if e.event is EventType.DISPUTED and "worker" in e.data and "slice" in e.data:
            key = (str(e.data["worker"]), int(e.data["slice"]))
            disputed.setdefault(key, set()).add(str(e.data["check"]))

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
                disputed=frozenset(disputed.get((worker, number), set())),
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


@dataclass(frozen=True, slots=True)
class WorkerState:
    name: str
    task: str
    session: str
    slices: int  # finished slices, infrastructure ones included
    session_total_micros: int  # the CLI's cumulative total for the session after the last slice
    fired: bool


@dataclass(frozen=True, slots=True)
class TaskState:
    task: str
    workers: tuple[str, ...]  # in hiring order; the last one is current
    best: str | None  # the worker whose latest gated slice passes the most checks
    passing: frozenset[str]  # checks passing in the best worker's latest gate run
    abandoned: bool

    @property
    def current(self) -> str | None:
        return self.workers[-1] if self.workers else None


@dataclass(frozen=True, slots=True)
class RunState:
    """Everything the round loop needs, rebuilt from events alone, so a run can be resumed."""

    workers: dict[str, WorkerState]
    tasks: dict[str, TaskState]
    closed_rounds: frozenset[int]
    approved_rounds: frozenset[int]
    stopped: bool

    def passing_total(self) -> int:
        return sum(len(t.passing) for t in self.tasks.values())


def run_state(events: Sequence[Event], task_ids: Sequence[str]) -> RunState:
    history = slice_history(events)
    fired = fired_workers(events)
    workers: dict[str, WorkerState] = {}
    by_task: dict[str, list[str]] = {task: [] for task in task_ids}
    for e in events:
        if e.event is EventType.HIRED and "worker" in e.data:
            name, task = str(e.data["worker"]), str(e.data.get("task", ""))
            totals = [
                x.data.get("session_total_micros")
                for x in events
                if x.event is EventType.SLICE_END and worker_name(x.actor) == name
            ]
            known = [t for t in totals if isinstance(t, int)]
            workers[name] = WorkerState(
                name=name,
                task=task,
                session=str(e.data.get("session", "")),
                slices=len(history.get(name, [])),
                session_total_micros=known[-1] if known else 0,
                fired=name in fired,
            )
            by_task.setdefault(task, []).append(name)
    abandoned = {str(e.data.get("task")) for e in events if e.event is EventType.ABANDONED}
    tasks = {}
    for task, names in by_task.items():
        # A replacement that did worse, or never ran, must not discard its predecessor's work:
        # the task's result is the best worker's, with later workers winning ties.
        best, passing = None, frozenset[str]()
        for name in names:
            latest = _latest_gated(history.get(name, []))
            if best is None or len(latest) >= len(passing):
                best, passing = name, latest
        tasks[task] = TaskState(
            task=task,
            workers=tuple(names),
            best=best,
            passing=passing,
            abandoned=task in abandoned,
        )
    return RunState(
        workers=workers,
        tasks=tasks,
        closed_rounds=frozenset(e.round for e in events if e.event is EventType.ROUND_CLOSED),
        approved_rounds=frozenset(
            int(e.data.get("round", 1))
            for e in events
            if e.event is EventType.APPROVED and e.actor == "investor"
        ),
        stopped=any(e.event is EventType.STOPPED for e in events),
    )


def _latest_gated(records: Sequence[SliceRecord]) -> frozenset[str]:
    """Checks passing after the last slice the gate ran on. Infrastructure slices are not gated,
    so they must not wipe out what passed before them."""
    for record in reversed(records):
        if record.outcome not in INFRASTRUCTURE:
            return record.passing
    return frozenset()
