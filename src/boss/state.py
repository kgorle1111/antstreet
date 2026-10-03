"""Run state rebuilt from ledger events. The ledger is the only source of truth, so the live
loop, offline replay and resume all read a run the same way.

Ledger data contract for stage 2 (keys inside each event's `data`):

    hired        boss        {worker, task, model, prompt}
    slice_start  worker:<w>  {slice, task, cap_micros, session}
    slice_end    worker:<w>  {slice, task, outcome, status, session_total_micros, denied_tools,
                              denial_reasons, ...}
                             with the event's cost_micros = this slice's own spend
    check_result gate        {check, task, status, detail, worker, slice}   after a slice
                 gate        {check, task, status, detail, scope: "product"}  the final product
                 gate        {check, status, detail, scope: "held_out"}  held-out, on the product
    fired        rule        {worker, task, reason, evidence}
    reassigned   boss        {task, from, to}
    blocked      worker:<w>  {task, reason}
    disputed     worker:<w>  {task, check, reason, worker, slice}
    round_closed boss        {passed, total, unlocked}
    approved     investor    {hashes} | {round} | {hashes, round, added_checks} (an amendment)
    started      boss        {config}
    resumed      investor    {}
    ruled        investor    {task, worker, ruling, check?, note?}   ruling: dropped|kept|unblocked
    topped_up    investor    {micros}   adds to the budget of the event's round
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from boss.budget import is_top_up
from boss.errors import INFRASTRUCTURE, Outcome
from boss.held_out import SCOPE as HELD_OUT_SCOPE
from boss.ledger import Event, EventType
from boss.rule import SliceRecord
from boss.rulings import DROPPED, KEPT, ruled


def worker_name(actor: str) -> str | None:
    return actor.removeprefix("worker:") if actor.startswith("worker:") else None


def slice_history(events: Sequence[Event]) -> dict[str, list[SliceRecord]]:
    """Per worker, its finished slices in order, each with the checks passing after it."""
    passing: dict[tuple[str, int], set[str]] = {}
    for e in events:
        if e.data.get("scope") == HELD_OUT_SCOPE:
            continue  # the workers never saw these: no per-worker decision may rest on them
        if e.event is EventType.CHECK_RESULT and "worker" in e.data and "slice" in e.data:
            key = (str(e.data["worker"]), int(e.data["slice"]))
            passing.setdefault(key, set())
            if e.data.get("status") == "passed":
                passing[key].add(str(e.data["check"]))

    # A dispute the investor has ruled on is settled: it no longer speaks for the worker.
    settled = ruled(events, KEPT) | ruled(events, DROPPED)
    disputed: dict[tuple[str, int], set[str]] = {}
    for e in events:
        if e.event is EventType.DISPUTED and "worker" in e.data and "slice" in e.data:
            key = (str(e.data["worker"]), int(e.data["slice"]))
            disputed.setdefault(key, set())
            if str(e.data["check"]) not in settled:
                disputed[key].add(str(e.data["check"]))

    inherited = _inherited_disputes(events, settled)
    dropped = ruled(events, DROPPED)  # a dropped check counts for nothing, passing or not
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
                outcome=_outcome(e),
                status=str(status),
                passing=frozenset(passing.get((worker, number), set())) - dropped,
                disputed=frozenset(disputed.get((worker, number), set()))
                | inherited.get(worker, set()),
                denied_tools=tuple(str(t) for t in e.data.get("denied_tools") or ()),
            )
        )
    return history


def _inherited_disputes(events: Sequence[Event], settled: frozenset[str]) -> dict[str, set[str]]:
    """Per worker, the checks that workers hired earlier for the same task disputed and the
    investor has not ruled on. A dispute is about a check, not about the worker who raised it: the
    rule must go on seeing it after that worker is fired, or a replacement whose only failing
    checks are those would be judged as if nobody had doubted them."""
    hired: list[tuple[str, str]] = []  # (worker, task) in hiring order
    for e in events:
        if e.event is EventType.HIRED and "worker" in e.data:
            hired.append((str(e.data["worker"]), str(e.data.get("task", ""))))
    order = {worker: i for i, (worker, _) in enumerate(hired)}
    raised = [
        (str(e.data["worker"]), str(e.data.get("task", "")), str(e.data["check"]))
        for e in events
        if e.event is EventType.DISPUTED and "worker" in e.data and "check" in e.data
    ]
    return {
        worker: {
            check
            for by, on, check in raised
            if on == task and check not in settled and order.get(by, len(order)) < order[worker]
        }
        for worker, task in hired
    }


def _outcome(event: Event) -> Outcome:
    """A slice's outcome. One this version does not know (a ledger written by a newer one) is
    refused by name: guessing would decide a firing or a charge on a guess."""
    raw = event.data.get("outcome", Outcome.CRASHED)
    try:
        return Outcome(raw)
    except ValueError:
        raise ValueError(
            f"slice_end of {event.actor} has an outcome this version does not know: {raw!r}"
        ) from None


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
    session: str | None  # the session to resume; None until a slice has got past infrastructure
    slices: int  # finished slices, infrastructure ones included
    session_total_micros: int  # the CLI's cumulative total for that session; 0 without one
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
    stopped: bool  # a stop that no later `resumed` event lifted
    locked_rounds: frozenset[int] = (
        frozenset()
    )  # closed below their unlock threshold, not topped up since
    dropped: frozenset[str] = frozenset()  # checks the investor dropped after a dispute

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
            session, session_total = _live_session(events, name, e.data.get("session"))
            workers[name] = WorkerState(
                name=name,
                task=task,
                session=session,
                slices=len(history.get(name, [])),
                session_total_micros=session_total,
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
    closed, locked = _closed_rounds(events)
    return RunState(
        workers=workers,
        tasks=tasks,
        closed_rounds=closed,
        approved_rounds=frozenset(
            int(e.data.get("round", 1))
            for e in events
            if e.event is EventType.APPROVED and e.actor == "investor"
        ),
        stopped=_stopped(events),
        dropped=ruled(events, DROPPED),
        locked_rounds=locked,
    )


def _closed_rounds(events: Sequence[Event]) -> tuple[frozenset[int], frozenset[int]]:
    """(closed, locked) rounds. An investor top-up recorded after a round closed below its unlock
    threshold reopens it: the one way past a lock. A top-up of any other round reopens nothing."""
    closed: set[int] = set()
    locked: set[int] = set()
    for e in events:
        if e.event is EventType.ROUND_CLOSED:
            closed.add(e.round)
            if not e.data.get("unlocked", False):
                locked.add(e.round)
        elif is_top_up(e) and e.round in locked:
            locked.discard(e.round)
            closed.discard(e.round)
    return frozenset(closed), frozenset(locked)


def _stopped(events: Sequence[Event]) -> bool:
    stopped = False
    for e in events:
        if e.event is EventType.STOPPED:
            stopped = True
        elif e.event is EventType.RESUMED and e.actor == "investor":
            stopped = False
    return stopped


def _live_session(
    events: Sequence[Event], worker: str, hired_session: object
) -> tuple[str | None, int]:
    """The session a worker's next slice should resume, and the CLI's cumulative cost for it.

    Every attempt that is not a resume starts a new session id, recorded on its slice_start: the
    CLI refuses an id that is already in use, and an interrupted or failed attempt may or may not
    have created one. A session is resumed only once a slice in it got past infrastructure and
    reported the session's total, which proves it exists. A slice that ends `session_lost` on the
    live session shows the CLI no longer has it: the next attempt starts a new one. Ledgers
    written before slice_start carried a session fall back to the one recorded at hiring.
    """
    fallback = str(hired_session) if hired_session else None
    live: str | None = None
    total, attempt = 0, fallback
    for e in events:
        if worker_name(e.actor) != worker:
            continue
        if e.event is EventType.SLICE_START:
            attempt = str(e.data.get("session") or fallback or "") or None
        elif e.event is EventType.SLICE_END:
            # The CLI's own result for the slice is the proof: it carries the session's total.
            # A slice that crashed or was killed before reporting proves nothing.
            known = e.data.get("session_total_micros")
            if _outcome(e) is Outcome.SESSION_LOST and attempt == live:
                live, total = None, 0  # the CLI no longer has it: the next attempt starts anew
            worked = _outcome(e) not in INFRASTRUCTURE
            if worked and isinstance(known, int) and attempt != live:
                live, total = attempt, 0
            if attempt == live and isinstance(known, int):
                total = known
    return live, total


def _latest_gated(records: Sequence[SliceRecord]) -> frozenset[str]:
    """Checks passing after the last slice the gate ran on. Infrastructure slices are not gated,
    so they must not wipe out what passed before them."""
    for record in reversed(records):
        if record.outcome not in INFRASTRUCTURE:
            return record.passing
    return frozenset()
