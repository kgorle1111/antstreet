"""The firm's round loop: fund workers one slice at a time, gate every slice, fire on evidence.

The loop keeps no state of its own. Before every decision it rebuilds the run from the ledger
(`state.run_state`), so an interrupted run resumes by calling `run_firm` again, and nothing is
spawned until `require_approval` finds an investor approval matching the term sheet and checks.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from boss import budget, handoff, limits, retry
from boss.approval import NotApprovedError, require_approval
from boss.boss import load_prompt
from boss.briefs import continuation_prompt, reassignment_brief, task_prompt
from boss.errors import INFRASTRUCTURE
from boss.gate import Check, CheckResult, run_gate
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.rule import Decision, FiringPolicy, decide
from boss.rundir import Recorder, RunPaths, assemble_product, slice_end_fields
from boss.runner import SliceRun, run_slice
from boss.state import RunState, run_state, slice_history
from boss.termsheet import Round, Task, TermSheet
from boss.worker import IsolationError, SliceSpec, billing_mode, disputed_checks, usd

BUILDER_PROMPT = "builder_v2.md"
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
        return [Check(c.id, c.file) for c in self.sheet.checks if c.task == task.id]

    def run_gate(self, task: Task, worker: str) -> list[CheckResult]:
        # Check files are read from disk on every gate run, so the approval is verified on
        # every gate run: a check edited mid-run never produces a recorded result.
        require_approval(self.events(), self.sheet, self.paths.checks)
        return self.gate(self.paths.workspace(worker), self.paths.checks, self.checks_of(task))

    def run(self) -> FirmReport:
        stopped: str | None = None
        total = len(self.sheet.checks)
        for round_ in self.sheet.rounds:
            state = self.state()
            if state.stopped:
                stopped = "stopped earlier"
                break
            if round_.n in state.closed_rounds:
                continue
            record = Recorder(self.ledger, self.run_id, round_.n)
            if round_.n not in state.approved_rounds and not self._approve(round_, record):
                stopped = "investor declined the round"
                break
            stopped = self._run_round(round_, record)
            passed = self.state().passing_total()
            unlocked = budget.unlocked(self.sheet, round_.n, passed)
            data = {"passed": passed, "total": total, "unlocked": unlocked}
            record("boss", EventType.ROUND_CLOSED, data=data)
            if stopped or passed == total:
                break
            if not unlocked:
                stopped = f"round {round_.n} closed below its unlock threshold"
                break
        assemble_product(self.paths, self.sheet, self.state())
        return FirmReport(self.state().passing_total(), total, stopped)

    def _approve(self, round_: Round, record: Recorder) -> bool:
        passed = self.state().passing_total()
        question = (
            f"Round {round_.n}: {passed}/{len(self.sheet.checks)} checks pass. "
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
            breached = self._breach(task, state)
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
                reason = "the term sheet or a check changed after the investor approved it"
                record("rule", EventType.STOPPED, data={"reason": reason})
                return f"stopped: {reason}"
            if stop:
                return stop

    def _breach(self, task: Task, state: RunState) -> str | None:
        """Why the run must stop before its next slice, if a hard limit is reached."""
        events, ts = self.events(), state.tasks[task.id]
        replaceable = ts.current is None or state.workers[ts.current].fired
        budgets = [budget.round_budget(self.sheet, events, r.n) for r in self.sheet.rounds]
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
        if current is None:
            self.paths.workspace(name).mkdir(parents=True, exist_ok=True)
        else:
            handoff.prepare_workspace(self.paths.workspace(current), self.paths.workspace(name))
            data = {"task": task.id, "from": current, "to": name}
            record("boss", EventType.REASSIGNED, data=data)
        hired = {"worker": name, "task": task.id, "session": str(uuid.uuid4())}
        hired |= {"model": self.config.model, "prompt": BUILDER_PROMPT}
        record("boss", EventType.HIRED, data=hired)
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
        # kn: a session exists once any slice got past infrastructure; resuming a session that was
        # never created would fail, so until then every attempt starts the session again.
        started = any(r.outcome not in INFRASTRUCTURE for r in history)
        require_approval(self.events(), self.sheet, self.paths.checks)  # before any spend
        disputed = frozenset().union(*(r.disputed for r in history))
        if started:
            prompt = continuation_prompt(self.run_gate(task, worker), disputed)
        else:
            prompt = self._first_prompt(task, worker, state)
        spec = SliceSpec(
            session_id=uuid.UUID(ws.session),
            resume=started,
            prompt=prompt,
            model=self.config.model,
            cap_micros=cap,
            append_system_prompt=load_prompt(BUILDER_PROMPT),
        )
        start = {"slice": number, "task": task.id, "cap_micros": cap}
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
        if run.outcome not in INFRASTRUCTURE:
            results = self.run_gate(task, worker)
            for r in results:
                data = {"check": r.check_id, "task": task.id, "status": str(r.status)}
                data |= {"detail": r.detail, "worker": worker, "slice": number}
                record("gate", EventType.CHECK_RESULT, data=data)
            # Only a check of this task that fails right now can be disputed, and only once.
            open_to_dispute = {r.check_id for r in results if not r.passed} - disputed
            for check, reason in disputed_checks(run.status, open_to_dispute).items():
                data = {"task": task.id, "check": check, "reason": reason}
                record(actor, EventType.DISPUTED, data=data | {"worker": worker, "slice": number})
        return self._act(task, worker, run, record)

    def _act(self, task: Task, worker: str, run: SliceRun, record: Recorder) -> str | None:
        history = slice_history(self.events())[worker]
        needed = frozenset(c.id for c in self.checks_of(task))
        verdict = decide(needed, history, self.config.policy)
        last_reason = (run.status or {}).get("reason")
        if verdict.decision is Decision.RETRY:
            return self._infrastructure(run, history, record)
        if verdict.decision is Decision.ESCALATE:
            if verdict.reason == "disputed":
                checks = ", ".join(verdict.evidence["disputed"])
                self.say(
                    f"Task {task.id} is set aside: its worker disputes {checks}. See the report."
                )
            else:
                blocked = {"task": task.id, "reason": last_reason}
                record(f"worker:{worker}", EventType.BLOCKED, data=blocked)
            # kn: an escalated task is set aside for this run; asking the investor to rule on it
            # (drop the check, keep it, unblock) comes with the interactive round prompt.
            record("boss", EventType.ABANDONED, data={"task": task.id, "reason": verdict.reason})
        elif verdict.decision is Decision.FIRE and (
            self.config.firing or verdict.reason == "slice limit"
        ):
            data = {"worker": worker, "task": task.id, "reason": verdict.reason}
            data |= {"evidence": verdict.evidence, "last_reason": last_reason}
            record("rule", EventType.FIRED, data=data)
        return None

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
    require_approval(read_events(paths.ledger), sheet, paths.checks)
    cfg = config or FirmConfig()
    firm = _Firm(
        sheet, paths, ledger, run_id, env, cfg, ask, say, slice_runner, gate, sleep, clock, clock()
    )
    return firm.run()
