"""The firm's round loop: fund workers one slice at a time, gate every slice, fire on evidence.

The loop keeps no state of its own. Before every decision it rebuilds the run from the ledger
(`state.run_state`), so an interrupted run resumes by calling `run_firm` again, and nothing is
spawned until `require_approval` finds an investor approval matching the term sheet and checks.
"""

from __future__ import annotations

import dataclasses
import shutil
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from boss import budget, handoff, limits, retry, rulings
from boss.approval import NotApprovedError, require_approval
from boss.boss import load_prompt
from boss.briefs import continuation_prompt, reassignment_brief, task_prompt
from boss.errors import INFRASTRUCTURE
from boss.gate import Check, CheckResult, run_gate
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.redact import safe_text
from boss.rule import Decision, FiringPolicy, Verdict, decide
from boss.rundir import Recorder, RunPaths, assemble_product, slice_end_fields
from boss.runner import SliceRun, run_slice
from boss.state import RunState, run_state, slice_history
from boss.termsheet import Round, Task, TermSheet
from boss.worker import (
    IsolationError,
    SliceSpec,
    billing_mode,
    disputed_checks,
    usd,
)

BUILDER_PROMPT = "builder_v3.md"
DEFAULT_WORKER_MODEL = "haiku"
DEFAULT_SLICE_MICROS = 100_000
MAX_WORKERS_PER_TASK = 2  # the first worker plus one reassignment
SLICE_SHARE = 0.8  # the single-agent benchmark arm caps its one slice at this share of the budget

SliceRunner = Callable[..., SliceRun]
Gate = Callable[..., list[CheckResult]]
Ask = Callable[[str], str]
Say = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class FirmConfig:
    model: str = DEFAULT_WORKER_MODEL
    slice_micros: int = DEFAULT_SLICE_MICROS
    reserve_micros: int = budget.RESERVE_MICROS  # held back from every cap: one model response
    policy: FiringPolicy = field(default_factory=FiringPolicy)
    firing: bool = True  # False: a stalled worker keeps being funded (the benchmark's control arm)
    limits: limits.RunLimits = field(default_factory=limits.RunLimits)


def config_data(config: FirmConfig) -> dict[str, Any]:
    """A FirmConfig as ledger data, so a run can be resumed with what it was started with."""
    return dataclasses.asdict(config)


def config_from_data(data: Mapping[str, Any]) -> FirmConfig:
    fields = dict(data)
    return FirmConfig(
        **fields
        | {
            "policy": FiringPolicy(**fields.get("policy", {})),
            "limits": limits.RunLimits(**fields.get("limits", {})),
        }
    )


def started_config(events: Sequence[Event]) -> FirmConfig | None:
    """The configuration recorded when the run first started, if it has started."""
    for e in events:
        if e.event is EventType.STARTED:
            return config_from_data(e.data["config"])
    return None


@dataclass(frozen=True, slots=True)
class FirmReport:
    passed: int
    total: int
    stopped: str | None  # why the run ended early, if it did

    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed == self.total


@dataclass(slots=True)
class _Firm:
    sheet: TermSheet
    paths: RunPaths
    ledger: LedgerWriter
    run_id: str
    env: Mapping[str, str]
    config: FirmConfig
    ask: Ask
    say: Say
    slice_runner: SliceRunner
    gate: Gate
    sleep: Callable[[float], None]
    clock: Callable[[], float]
    started: float

    def events(self) -> list[Event]:
        return read_events(self.paths.ledger)

    def state(self) -> RunState:
        return run_state(self.events(), [t.id for t in self.sheet.tasks])

    def checks_of(self, task: Task) -> list[Check]:
        """The task's checks that still count: one the investor dropped is no longer run."""
        dropped = rulings.ruled(self.events(), rulings.DROPPED)
        return [
            Check(c.id, c.file)
            for c in self.sheet.checks
            if c.task == task.id and c.id not in dropped
        ]

    def required(self) -> int:
        return len(self.sheet.checks) - len(self.state().dropped)

    def run_gate(self, task: Task, worker: str) -> list[CheckResult]:
        # Check files are read from disk on every gate run, so the approval is verified on
        # every gate run: a check edited mid-run never produces a recorded result.
        require_approval(self.events(), self.sheet, self.paths.checks)
        return self.gate(self.paths.workspace(worker), self.paths.checks, self.checks_of(task))

    def run(self) -> FirmReport:
        stopped: str | None = None
        for round_ in self.sheet.rounds:
            state = self.state()
            if state.stopped:
                stopped = "stopped earlier"
                break
            if round_.n in state.locked_rounds:  # also on resume: a locked round stays locked
                stopped = f"round {round_.n} closed below its unlock threshold"
                break
            if round_.n in state.closed_rounds:
                continue
            record = Recorder(self.ledger, self.run_id, round_.n)
            if round_.n not in state.approved_rounds and not self._approve(round_, record):
                stopped = "investor declined the round"
                break
            stopped = self._run_round(round_, record)
            if stopped:  # paused or stopped mid-round: it stays open, so a resume continues it
                break
            passed, total = self.state().passing_total(), self.required()
            unlocked = budget.unlocked(self.sheet, round_.n, passed, total)
            data = {"passed": passed, "total": total, "unlocked": unlocked}
            record("boss", EventType.ROUND_CLOSED, data=data)
            if passed == total:
                break
            if not unlocked:
                stopped = f"round {round_.n} closed below its unlock threshold"
                break
        for path in assemble_product(self.paths, self.sheet, self.state()):
            self.say(f"Not in the product: {path} (its name collides with another task's file).")
        return FirmReport(self.state().passing_total(), self.required(), stopped)

    def _approve(self, round_: Round, record: Recorder) -> bool:
        passed = self.state().passing_total()
        question = (
            f"Round {round_.n}: {passed}/{self.required()} checks pass. "
            f"Fund ${usd(round_.budget_micros)} more? [y]es / [n]o "
        )
        try:
            answer = self.ask(question).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("y", "yes", "a", "approve"):
            record("investor", EventType.APPROVED, data={"round": round_.n})
            return True
        record("investor", EventType.STOPPED, data={"reason": f"round {round_.n} not funded"})
        return False

    def _run_round(self, round_: Round, record: Recorder) -> str | None:
        """Fund slices until every task is done or abandoned, or the round runs out of money."""
        while True:
            state = self.state()
            task = self._next_task(state)
            if task is None:
                return None
            current = state.tasks[task.id].current
            if current is not None and not state.workers[current].fired:
                # After an interruption the last slice may not have been gated or acted on yet.
                before = len(self.events())
                try:
                    self._gate_slice(task, current, record)
                except NotApprovedError:
                    return self._tampered(record)
                self._act(task, current, record, None)
                if len(self.events()) != before:
                    continue
            breached = self._breach(task, state, round_)
            if breached:
                record("rule", EventType.STOPPED, data={"reason": breached})
                return f"stopped: {breached}"
            left = budget.remaining(self.sheet, self.events(), round_.n)
            cap = budget.next_slice_cap(
                left,
                slice_micros=self.config.slice_micros,
                reserve_micros=self.config.reserve_micros,
            )
            if cap is None:  # checked before hiring, so nobody is hired into an empty round
                reserve = usd(self.config.reserve_micros)
                self.say(
                    f"Round {round_.n} cannot fund another slice: ${usd(max(left, 0))} left, "
                    f"${reserve} of it reserved for one response running past its cap."
                )
                return None
            worker = self._current_worker(task, state, record)
            if worker is None:
                continue  # the task was just abandoned; pick the next one
            try:
                stop = self._slice(task, worker, cap, record)
            except NotApprovedError:
                return self._tampered(record)
            if stop:
                return stop

    def _tampered(self, record: Recorder) -> str:
        reason = "the term sheet or a check changed after the investor approved it"
        record("rule", EventType.STOPPED, data={"reason": reason})
        return f"stopped: {reason}"

    def _breach(self, task: Task, state: RunState, round_: Round) -> str | None:
        """Why the run must stop before its next slice, if a hard limit is reached."""
        events, ts = self.events(), state.tasks[task.id]
        replaceable = ts.current is None or state.workers[ts.current].fired
        # Only rounds the investor has funded so far count toward the ceiling.
        funded = [r.n for r in self.sheet.rounds if r.n <= round_.n]
        budgets = [budget.round_budget(self.sheet, events, n) for n in funded]
        return limits.breach(
            events,
            self.config.limits,
            ceiling_micros=limits.spend_ceiling(budgets, self.config.reserve_micros),
            elapsed_s=self.clock() - self.started,
            hiring=replaceable and len(ts.workers) < MAX_WORKERS_PER_TASK,
        )

    def _next_task(self, state: RunState) -> Task | None:
        for task in self.sheet.tasks:
            ts = state.tasks[task.id]
            if not ts.abandoned and not {c.id for c in self.checks_of(task)} <= ts.passing:
                return task
        return None

    def _current_worker(self, task: Task, state: RunState, record: Recorder) -> str | None:
        ts = state.tasks[task.id]
        current = ts.current
        if current is not None and not state.workers[current].fired:
            return current
        if len(ts.workers) >= MAX_WORKERS_PER_TASK:
            data = {"task": task.id, "reason": "already reassigned once"}
            record("boss", EventType.ABANDONED, data=data)
            return None
        name = f"w{len(state.workers) + 1}"
        # No hire is on the ledger under this name, so a folder of that name is what an
        # interrupted hire left behind. It is inside this run's own folder.
        shutil.rmtree(self.paths.workspace(name), ignore_errors=True)
        if current is None:
            self.paths.workspace(name).mkdir(parents=True, exist_ok=True)
        else:
            handoff.prepare_workspace(self.paths.workspace(current), self.paths.workspace(name))
            data = {"task": task.id, "from": current, "to": name}
            record("boss", EventType.REASSIGNED, data=data)
        hired = {"worker": name, "task": task.id, "model": self.config.model}
        record("boss", EventType.HIRED, data=hired | {"prompt": BUILDER_PROMPT})
        return name

    def _first_prompt(self, task: Task, worker: str, state: RunState) -> str:
        prompt = task_prompt(self.sheet, task, self.paths.checks)
        previous = [w for w in state.tasks[task.id].workers if w != worker]
        if not previous:
            return prompt
        old, events = previous[-1], self.events()
        return reassignment_brief(
            prompt,
            fired=next(e for e in reversed(events) if _fired(e, old)),
            history=slice_history(events)[old],
            gate_results=self.run_gate(task, old),
            kept=self.paths.workspace(worker) / handoff.PREVIOUS_DIR,
        )

    def _slice(self, task: Task, worker: str, cap: int, record: Recorder) -> str | None:
        state = self.state()
        ws = state.workers[worker]
        actor, number = f"worker:{worker}", ws.slices + 1
        history = slice_history(self.events()).get(worker, [])
        require_approval(self.events(), self.sheet, self.paths.checks)  # before any spend
        disputed = frozenset().union(*(r.disputed for r in history))
        # A session is resumed only once the ledger proves it exists (state._live_session). Any
        # other attempt gets a new id: the CLI refuses one that is already in use (probe, CLI
        # 2.1.285), and an interrupted attempt leaves no record of whether it created its session.
        resume = ws.session is not None
        session = ws.session or str(uuid.uuid4())
        if resume:
            events = self.events()
            prompt = continuation_prompt(
                self.run_gate(task, worker),
                disputed,
                history[-1].denied_tools,
                task.paths[0],
                rulings.notes_since(events, task.id, _after_last_slice(events, worker)),
            )
        else:
            prompt = self._first_prompt(task, worker, state)
        spec = SliceSpec(
            session_id=uuid.UUID(session),
            resume=resume,
            prompt=prompt,
            model=self.config.model,
            cap_micros=cap,
            append_system_prompt=load_prompt(BUILDER_PROMPT),
        )
        start = {"slice": number, "task": task.id, "cap_micros": cap, "session": session}
        record(actor, EventType.SLICE_START, data=start)
        try:
            run = self.slice_runner(
                spec, self.paths.workspace(worker), self.paths.log(worker), env=self.env
            )
        except IsolationError as exc:
            record(actor, EventType.ERROR, cost_micros=None, data={"isolation": str(exc)})
            record("boss", EventType.STOPPED, data={"reason": "worker did not start isolated"})
            raise
        fields = slice_end_fields(run, number, task.id, ws.session_total_micros)
        record(actor, EventType.SLICE_END, billing=billing_mode(self.env), **fields)
        self._gate_slice(task, worker, record, run.status)
        return self._act(task, worker, record, run)

    def _gate_slice(self, task: Task, worker: str, record: Recorder, status: object = None) -> None:
        """Gate the worker's last slice and record what it disputes, unless that is already on
        the ledger. `status` is the worker's raw report; after an interruption it is gone, so
        only the gate's results are recovered and the worker may raise its disputes again."""
        events = self.events()
        history = slice_history(events).get(worker, [])
        if not history or history[-1].outcome in INFRASTRUCTURE:
            return
        number = history[-1].slice
        if any(_gated(e, worker, number) for e in events):
            return
        results = self.run_gate(task, worker)
        for r in results:
            data = {"check": r.check_id, "task": task.id, "status": str(r.status)}
            data |= {"detail": r.detail, "worker": worker, "slice": number}
            record("gate", EventType.CHECK_RESULT, data=data)
        # Only a check of this task that fails right now can be disputed, once, and never one
        # the investor has ruled on.
        raised = frozenset().union(*(r.disputed for r in history))
        settled = rulings.ruled(events, rulings.KEPT)
        open_to_dispute = {r.check_id for r in results if not r.passed} - raised - settled
        if isinstance(status, dict):
            for check, reason in disputed_checks(status, open_to_dispute).items():
                data = {"task": task.id, "check": check, "reason": reason}
                data |= {"worker": worker, "slice": number}
                record(f"worker:{worker}", EventType.DISPUTED, data=data)

    def _act(self, task: Task, worker: str, record: Recorder, run: SliceRun | None) -> str | None:
        """Apply the rule to the worker's history. `run` is the slice that just finished; None
        when recovering after an interruption, where only a firing or an escalation can still be
        owed. Safe to call again: it records nothing that is already on the ledger."""
        events = self.events()
        history = slice_history(events).get(worker, [])
        needed = frozenset(c.id for c in self.checks_of(task))
        if not history or not needed:
            return None
        verdict = decide(needed, history, self.config.policy)
        if verdict.decision is Decision.RETRY:
            return self._infrastructure(run, history, record) if run else None
        since = _after_last_slice(events, worker)
        if verdict.decision is Decision.ESCALATE:
            if not any(_settles(e, task.id) for e in events[since:]):
                self._escalate(task, worker, verdict, events, since, record)
        elif verdict.decision is Decision.FIRE and (
            self.config.firing or verdict.reason == "slice limit"
        ):
            data = {"worker": worker, "task": task.id, "reason": verdict.reason}
            data |= {"evidence": verdict.evidence, "last_reason": _last_reason(events, worker)}
            record("rule", EventType.FIRED, data=data)
        return None

    def _escalate(
        self,
        task: Task,
        worker: str,
        verdict: Verdict,
        events: Sequence[Event],
        since: int,
        record: Recorder,
    ) -> None:
        """Put to the investor what the worker could not settle. No clear ruling sets the task
        aside; nothing is ever decided for the investor."""
        if verdict.reason == "disputed":
            described = {c.id: c.description for c in self.sheet.checks}
            reasons = {
                e.data.get("check"): str(e.data.get("reason", ""))
                for e in events
                if e.event is EventType.DISPUTED and e.data.get("worker") == worker
            }
            for check in verdict.evidence["disputed"]:
                ruling = rulings.ask_dispute(
                    self.ask,
                    task=task.id,
                    worker=worker,
                    check=check,
                    description=safe_text(" ".join(described.get(check, "").split()), limit=200),
                    reason=reasons.get(check, ""),
                )
                if ruling is None:
                    self.say(f"Task {task.id} is set aside: {worker} disputes {check}.")
                    record(
                        "boss", EventType.ABANDONED, data={"task": task.id, "reason": "disputed"}
                    )
                    return
                ruled = {"task": task.id, "worker": worker, "check": check, "ruling": ruling}
                record("investor", EventType.RULED, data=ruled)
            return
        reason = _last_reason(events, worker) or verdict.reason
        if not any(e.event is EventType.BLOCKED for e in events[since:]):
            blocked = {"task": task.id, "reason": _last_reason(events, worker)}
            record(f"worker:{worker}", EventType.BLOCKED, data=blocked)
        note = rulings.ask_block(self.ask, task=task.id, worker=worker, reason=reason)
        if note is None:
            record("boss", EventType.ABANDONED, data={"task": task.id, "reason": verdict.reason})
            return
        ruled = {"task": task.id, "worker": worker, "ruling": rulings.UNBLOCKED, "note": note}
        record("investor", EventType.RULED, data=ruled)

    def _infrastructure(self, run: SliceRun, history: list[Any], record: Recorder) -> str | None:
        attempt = 0
        for r in reversed(history):
            if r.outcome not in INFRASTRUCTURE:
                break
            attempt += 1
        action = retry.infra_action(run.outcome, attempt, run.rate_limit)
        if isinstance(action, retry.Wait):
            self.say(f"{action.reason}; waiting {action.seconds:.0f}s")
            self.sleep(action.seconds)
            return None
        if isinstance(action, retry.Pause):
            data = {"reason": action.reason, "until_epoch": action.until_epoch}
            record("boss", EventType.PAUSED, data=data)
            return f"paused: {action.reason}"
        record("boss", EventType.STOPPED, data={"reason": action.reason, "fix": action.fix})
        return f"stopped: {action.reason}"


def _after_last_slice(events: Sequence[Event], worker: str) -> int:
    """Index just past the worker's last finished slice (0 if it has none)."""
    actor = f"worker:{worker}"
    ends = [i for i, e in enumerate(events) if e.event is EventType.SLICE_END and e.actor == actor]
    return ends[-1] + 1 if ends else 0


def _last_reason(events: Sequence[Event], worker: str) -> str | None:
    """The reason the worker gave at its last slice, as cleaned for the ledger."""
    since = _after_last_slice(events, worker)
    status = events[since - 1].data.get("status") if since else None
    return (status or {}).get("reason") or None


def _gated(event: Event, worker: str, number: int) -> bool:
    data = event.data
    found = event.event is EventType.CHECK_RESULT
    return found and data.get("worker") == worker and data.get("slice") == number


def _settles(event: Event, task: str) -> bool:
    """Whether this event already settles an escalation of the task."""
    ruling = event.event is EventType.RULED and event.actor == "investor"
    return (ruling or event.event is EventType.ABANDONED) and event.data.get("task") == task


def _fired(event: Event, worker: str) -> bool:
    return event.event is EventType.FIRED and event.data.get("worker") == worker


def run_firm(
    sheet: TermSheet,
    paths: RunPaths,
    ledger: LedgerWriter,
    run_id: str,
    *,
    env: Mapping[str, str],
    config: FirmConfig | None = None,
    ask: Ask = input,
    say: Say = print,
    slice_runner: SliceRunner = run_slice,
    gate: Gate = run_gate,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> FirmReport:
    events = read_events(paths.ledger)
    require_approval(events, sheet, paths.checks)
    cfg = config or started_config(events) or FirmConfig()
    if started_config(events) is None:
        start = Event(run=run_id, round=0, actor="boss", event=EventType.STARTED)
        ledger.append(dataclasses.replace(start, data={"config": config_data(cfg)}))
    firm = _Firm(
        sheet, paths, ledger, run_id, env, cfg, ask, say, slice_runner, gate, sleep, clock, clock()
    )
    return firm.run()
