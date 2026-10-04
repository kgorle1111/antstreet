"""The firm's round loop: fund workers one slice at a time, gate every slice, fire on evidence.

The loop keeps no state of its own. Before every decision it rebuilds the run from the ledger
(`state.run_state`), so an interrupted run resumes by calling `run_firm` again, and nothing is
spawned until `require_approval` finds an investor approval matching the term sheet and checks.
"""

from __future__ import annotations

import dataclasses
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from boss import budget, handoff, limits, retry, rulings
from boss import held_out as held_out_store
from boss.approval import NotApprovedError, require_approval
from boss.boss import load_prompt
from boss.briefs import (
    added_checks_note,
    continuation_prompt,
    predecessor_disputes_note,
    reassignment_brief,
    task_prompt,
)
from boss.errors import INFRASTRUCTURE, Outcome
from boss.gate import Check, CheckResult, run_gate
from boss.ledger import Event, EventType, LedgerWriter
from boss.redact import safe_text
from boss.roles.builders import builder_system_prompt
from boss.rule import Decision, FiringPolicy, Verdict, decide
from boss.rundir import (
    Recorder,
    RunPaths,
    WorkspaceTooBig,
    assemble_product,
    slice_end_fields,
    workspace_bytes,
)
from boss.runner import SliceRun, run_slice
from boss.state import RunState, run_state, slice_history
from boss.termsheet import Round, Task, TermSheet
from boss.worker import (
    IsolationError,
    SliceSpec,
    billing_mode,
    check_thinking,
    disputed_checks,
    usd,
)

BUILDER_PROMPT = "builder_v4.md"
DEFAULT_WORKER_MODEL = "haiku"
DEFAULT_SLICE_MICROS = 100_000
MAX_WORKERS_PER_TASK = 2  # the first worker plus one reassignment
SLICE_SHARE = 0.8  # the single-agent benchmark arm caps its one slice at this share of the budget

SliceRunner = Callable[..., SliceRun]
Gate = Callable[..., list[CheckResult]]
# (check id, the worker's reason) -> a line to show the investor, or None. Advice binds nothing.
Advise = Callable[[str, str], str | None]
Ask = Callable[[str], str]
_CANNOT_GATE = (NotApprovedError, WorkspaceTooBig)
Say = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class FirmConfig:
    model: str = DEFAULT_WORKER_MODEL
    slice_micros: int = DEFAULT_SLICE_MICROS
    # Held back from every cap: one response of `model`. MODEL_RESERVE resolves to its figure.
    reserve_micros: int = budget.MODEL_RESERVE
    policy: FiringPolicy = field(default_factory=FiringPolicy)
    firing: bool = True  # False: a stalled worker keeps being funded (the benchmark's control arm)
    limits: limits.RunLimits = field(default_factory=limits.RunLimits)
    parallel: int = 1  # tasks worked on at once; each task still has one worker at a time
    # A worker profile (roles.builders): skills appended to the builder prompt. None is the
    # bare prompt, the default until a profile is measured to be worth its tokens.
    profile: str | None = None
    # Pause the run once a slice reports a plan window this full (a fraction), instead of running
    # into the limit mid-slice and losing that slice. None turns the pause off.
    plan_pause_at: float | None = 0.95
    # How many held-out checks the examiner was asked for (0 turns the feature off). The checks
    # themselves are in the run folder and in the investor's approval; this records the request,
    # so the report can say when it was not met.
    # The examiner runs before the approval (`boss fund --held-out N`), so the loop only grades
    # what was approved.
    held_out: int = 0
    # The CLI's thinking budget for every worker slice (MAX_THINKING_TOKENS); 0 turns thinking
    # off. None leaves the CLI's own default.
    thinking_tokens: int | None = None

    def __post_init__(self) -> None:
        check_thinking(self.thinking_tokens)
        if self.reserve_micros == budget.MODEL_RESERVE:
            object.__setattr__(self, "reserve_micros", budget.reserve_for(self.model))
        if type(self.held_out) is not int or not 0 <= self.held_out <= held_out_store.MAX_HELD_OUT:
            raise ValueError(
                f"held_out must be a whole number from 0 to {held_out_store.MAX_HELD_OUT}, "
                f"got {self.held_out!r}"
            )


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
    held_out_passed: int = 0  # held-out checks passing on the product; total 0 when there are none
    held_out_total: int = 0

    @property
    def all_passed(self) -> bool:
        """Every visible check and, when the run has held-out checks, every one of them too."""
        visible = self.total > 0 and self.passed == self.total
        return visible and self.held_out_passed == self.held_out_total


@dataclass(frozen=True, slots=True)
class _Pending:
    """A slice that is planned and about to run."""

    task: Task
    worker: str
    number: int
    spec: SliceSpec
    start: dict[str, Any]  # the slice_start event's data
    previous_total: int  # the session's running total before this slice
    previous_tokens: tuple[int, int, int]  # its token totals: in, out, cached


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
    cancel: threading.Event  # set on Ctrl-C so slices running in other threads stop
    advise: Advise | None  # an opinion to show the investor before a dispute is ruled on

    def events(self) -> list[Event]:
        return self.paths.events()

    def require_approval(self, events: Sequence[Event]) -> None:
        """The investor's approval must match the checks and the held-out folder on disk now."""
        require_approval(
            events,
            self.sheet,
            self.paths.checks,
            self.paths.held_out,
            self.paths.investor_key,
            self.paths.rules,
        )

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
        self.require_approval(self.events())
        limit = self.config.limits.max_workspace_bytes
        size = workspace_bytes(self.paths.workspace(worker), limit)
        if size > limit:
            raise WorkspaceTooBig(worker, size, limit)
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
            unopened = round_.n not in state.approved_rounds
            if unopened and self._next_task(state) is None and state.workers:
                break  # nothing is left to do: no further round is opened or paid for
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
        passed = self._gate_product()
        held_passed, held_total = self._gate_held_out()
        return FirmReport(passed, self.required(), stopped, held_passed, held_total)

    def _gate_product(self) -> int:
        """Run every required check on the assembled product and return how many pass.

        Each task was gated in its own worker's folder; what the investor receives is product/,
        where several tasks' files meet. This is the verdict on what is delivered. It is
        recorded once per product: running a finished run again adds nothing.
        """
        events = self.events()
        workspace_passes = self.state().passing_total()
        last_slice = _last_slice(events)
        if last_slice < 0:
            return workspace_passes  # nothing was built
        dropped = self.state().dropped
        required = [Check(c.id, c.file) for c in self.sheet.checks if c.id not in dropped]
        tasks = {c.id: c.task for c in self.sheet.checks}
        over = "The product is over the folder size limit, so it was not gated."
        verdicts = self._grade_product(
            events, last_slice, "product", required, self.paths.checks, tasks, over
        )
        if verdicts is None:
            return workspace_passes  # the checks changed: only earlier results can be trusted
        passed = sum(verdicts.get(c.id, False) for c in required)
        if passed != workspace_passes:
            self.say(
                f"The assembled product passes {passed} checks; the workers' own folders "
                f"passed {workspace_passes}. The product's figure is the one reported."
            )
        return passed

    def _gate_held_out(self) -> tuple[int, int]:
        """Grade the held-out checks on the assembled product: (passed, total), (0, 0) when the
        run has none. Completed like the product verdict: a resume grades only the checks with no
        result yet. A check that could not be graded counts as not passed."""
        checks = held_out_store.load(self.paths.held_out)
        if not checks:
            return 0, 0
        events, total = self.events(), len(checks)
        last_slice = _last_slice(events)
        if last_slice < 0:
            return 0, total  # nothing was built
        over = "The product is over the folder size limit, so the held-out checks were not run."
        verdicts = self._grade_product(
            events,
            last_slice,
            held_out_store.SCOPE,
            [c.to_check() for c in checks],
            self.paths.held_out,
            None,
            over,
        )
        passed = 0 if verdicts is None else sum(verdicts.get(c.id, False) for c in checks)
        self.say(
            f"Held-out checks: {passed} of {total} passed on the product; "
            "the workers never saw them."
        )
        return passed, total

    def _grade_product(
        self,
        events: Sequence[Event],
        last_slice: int,
        scope: str,
        required: Sequence[Check],
        checks_dir: Path,
        tasks: Mapping[str, str] | None,
        over: str,
    ) -> dict[str, bool] | None:
        """Each required check's verdict on product/ for results of this `scope` recorded since
        the last slice, running (and recording) the checks that have none. None when the product
        cannot be gated: it is over the size limit, or the approval no longer matches the files."""
        verdicts = {
            e.data["check"]: e.data.get("status") == "passed"
            for e in events[last_slice:]
            if e.event is EventType.CHECK_RESULT and e.data.get("scope") == scope
        }
        # A run killed between two results leaves the verdict on some checks only: the ones
        # still missing are gated now.
        missing = [c for c in required if c.id not in verdicts]
        limit = self.config.limits.max_workspace_bytes
        if missing and workspace_bytes(self.paths.product, limit) > limit:
            self.say(over)
            return None
        if missing:
            try:
                self.require_approval(events)
                results = self.gate(self.paths.product, checks_dir, missing)
            except NotApprovedError:
                return None
            record = Recorder(self.ledger, self.run_id, events[last_slice].round)
            for r in results:
                data: dict[str, Any] = {"check": r.check_id, "status": str(r.status)}
                if tasks is not None:
                    data["task"] = tasks[r.check_id]
                record(
                    "gate",
                    EventType.CHECK_RESULT,
                    data=data | {"detail": r.detail, "scope": scope, "sandboxed": r.sandboxed},
                )
                verdicts[r.check_id] = r.passed
        return verdicts

    def _approve(self, round_: Round, record: Recorder) -> bool:
        passed = self.state().passing_total()
        funding = budget.round_budget(self.sheet, self.events(), round_.n)  # with any top-ups
        question = (
            f"Round {round_.n}: {passed}/{self.required()} checks pass. "
            f"Fund ${usd(funding)} more? [y]es / [n]o "
        )
        try:
            answer = self.ask(question).strip().lower()
        except EOFError:  # nobody is there to fund it; Ctrl-C is an interruption, not a no
            answer = "n"
        if answer in ("y", "yes", "a", "approve"):
            record("investor", EventType.APPROVED, data={"round": round_.n})
            return True
        record("investor", EventType.STOPPED, data={"reason": f"round {round_.n} not funded"})
        return False

    def _run_round(self, round_: Round, record: Recorder) -> str | None:
        """Fund slices, up to `config.parallel` tasks at a time, until every task is done or set
        aside, or the round runs out of money. Only this thread writes the ledger."""
        while True:
            plans, outcome = self._plan_wave(round_, record)
            if plans is None:
                return outcome
            if not plans:
                continue  # something was recorded (a recovery, an abandonment): look again
            try:
                wave = [self._prepare(task, worker, cap) for task, worker, cap in plans]
            except _CANNOT_GATE as exc:
                return self._halt(record, exc)
            for pending in wave:
                record(f"worker:{pending.worker}", EventType.SLICE_START, data=pending.start)
            stop = self._finish_wave(wave, self._run_wave(wave), record)
            if stop:
                return stop

    def _plan_wave(
        self, round_: Round, record: Recorder
    ) -> tuple[list[tuple[Task, str, int]] | None, str | None]:
        """Which tasks get a slice now, with which worker and cap. `None` plans end the round,
        with the reason if the run must stop; empty plans mean the ledger changed and the state
        must be read again."""
        state = self.state()
        open_tasks = self._open_tasks(state)
        if not open_tasks:
            return None, None
        before = len(self.events())
        for task in open_tasks:  # after an interruption a slice may not be gated or acted on
            current = state.tasks[task.id].current
            if current is not None and not state.workers[current].fired:
                try:
                    self._gate_slice(task, current, record)
                except _CANNOT_GATE as exc:
                    return None, self._halt(record, exc)
                self._act(task, current, record, None)
        if len(self.events()) != before:
            return [], None
        plans: list[tuple[Task, str, int]] = []
        left = budget.remaining(self.sheet, self.events(), round_.n)
        for task in open_tasks[: max(1, self.config.parallel)]:
            state = self.state()
            breached = self._breach(task, state, round_, len(plans))
            if breached:
                if plans:
                    break  # run what is planned; the limit stops the run on the next pass
                record("rule", EventType.STOPPED, data={"reason": breached})
                return None, f"stopped: {breached}"
            # Slices of one wave run at once, so each later one leaves room for the overshoot
            # of every earlier one as well as its own.
            cap = budget.next_slice_cap(
                left - sum(c for _, _, c in plans),
                slice_micros=self.config.slice_micros,
                reserve_micros=self.config.reserve_micros * (len(plans) + 1),
            )
            if cap is None:  # checked before hiring, so nobody is hired into an empty round
                if plans:
                    break
                reserve = usd(self.config.reserve_micros)
                self.say(
                    f"Round {round_.n} cannot fund another slice: ${usd(max(left, 0))} left, "
                    f"${reserve} of it reserved for one response running past its cap."
                )
                return None, None
            worker = self._current_worker(task, state, record)
            if worker is not None:
                plans.append((task, worker, cap))
        return plans, None

    def _run_wave(self, wave: list[_Pending]) -> list[SliceRun | BaseException]:
        """Run the wave's slices, at once if there are several. Returns each slice's run, or
        what it raised, in the wave's order."""

        def run(pending: _Pending) -> SliceRun:
            return self.slice_runner(
                pending.spec,
                self.paths.workspace(pending.worker),
                self.paths.log(pending.worker),
                env=self.env,
            )

        if len(wave) == 1:
            try:
                return [run(wave[0])]
            except IsolationError as exc:
                return [exc]
        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            futures = [pool.submit(run, pending) for pending in wave]
            try:
                wait(futures)
            except KeyboardInterrupt:
                self.cancel.set()  # the slice runners stop their processes and return
                wait(futures)
                raise
        results: list[SliceRun | BaseException] = []
        for future in futures:
            error = future.exception()
            if isinstance(error, KeyboardInterrupt):
                raise error
            results.append(error if error is not None else future.result())
        return results

    def _finish_wave(
        self, wave: list[_Pending], results: list[SliceRun | BaseException], record: Recorder
    ) -> str | None:
        """Book every slice first, so no known cost is lost, then gate and judge each."""
        failure: BaseException | None = None
        finished: list[tuple[_Pending, SliceRun]] = []
        for pending, result in zip(wave, results, strict=True):
            actor = f"worker:{pending.worker}"
            if isinstance(result, IsolationError):
                record(actor, EventType.ERROR, cost_micros=None, data={"isolation": str(result)})
                failure = failure or result
            elif isinstance(result, BaseException):
                failure = failure or result
            else:
                fields = slice_end_fields(
                    result,
                    pending.number,
                    pending.task.id,
                    pending.previous_total,
                    pending.previous_tokens,
                )
                record(actor, EventType.SLICE_END, billing=billing_mode(self.env), **fields)
                finished.append((pending, result))
        if isinstance(failure, IsolationError):
            record("boss", EventType.STOPPED, data={"reason": "worker did not start isolated"})
        if failure is not None:
            raise failure
        stop: str | None = None
        for pending, run in finished:
            try:
                self._gate_slice(pending.task, pending.worker, record, run.status)
            except _CANNOT_GATE as exc:
                return self._halt(record, exc)
            self._status_line(pending.task, pending.worker, pending.number, record.round)
            stop = self._act(pending.task, pending.worker, record, run) or stop
        return stop or self._plan_pressure([run for _, run in finished], record)

    def _plan_pressure(self, runs: Sequence[SliceRun], record: Recorder) -> str | None:
        """Pause while there is still work and the plan is nearly used up."""
        if self.config.plan_pause_at is None or self._next_task(self.state()) is None:
            return None
        for run in runs:
            pause = retry.plan_pressure(run.rate_limit, threshold=self.config.plan_pause_at)
            if pause is not None:
                data = {"reason": pause.reason, "until_epoch": pause.until_epoch}
                record("boss", EventType.PAUSED, data=data)
                return f"paused: {pause.reason}"
        return None

    def _halt(self, record: Recorder, why: Exception) -> str:
        """Stop the run because the gate must not run: the checks changed, or a folder is too
        big to copy."""
        reason = str(why)
        if isinstance(why, NotApprovedError):
            reason = "the term sheet or a check changed after the investor approved it"
        record("rule", EventType.STOPPED, data={"reason": reason})
        return f"stopped: {reason}"

    def _breach(self, task: Task, state: RunState, round_: Round, planned: int = 0) -> str | None:
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
            planned_slices=planned,
        )

    def _open_tasks(self, state: RunState) -> list[Task]:
        """Tasks that still have a required check failing and were not set aside, in order."""
        return [
            task
            for task in self.sheet.tasks
            if not state.tasks[task.id].abandoned
            and not {c.id for c in self.checks_of(task)} <= state.tasks[task.id].passing
        ]

    def _next_task(self, state: RunState) -> Task | None:
        return next(iter(self._open_tasks(state)), None)

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
        hired: dict[str, Any] = {"worker": name, "task": task.id, "model": self.config.model}
        hired |= {"prompt": BUILDER_PROMPT, "profile": self.config.profile}
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

    def _builder_prompt(self) -> str:
        if self.config.profile is None:
            return load_prompt(BUILDER_PROMPT)
        return builder_system_prompt(self.config.profile, BUILDER_PROMPT)

    def _prepare(self, task: Task, worker: str, cap: int) -> _Pending:
        """Everything a slice needs, decided before its start is recorded. Writes nothing."""
        state = self.state()
        ws = state.workers[worker]
        history = slice_history(self.events()).get(worker, [])
        self.require_approval(self.events())  # before any spend
        disputed = frozenset().union(*(r.disputed for r in history))
        # A session is resumed only once the ledger proves it exists (state._live_session). Any
        # other attempt gets a new id: the CLI refuses one that is already in use (probe, CLI
        # 2.1.285), and an interrupted attempt leaves no record of whether it created its session.
        resume = ws.session is not None
        session = ws.session or str(uuid.uuid4())
        events = self.events()
        since = _after_last_slice(events, worker)
        notes = rulings.notes_since(events, task.id, since, worker)
        mine = {c.id for c in self.checks_of(task)}
        # What an earlier worker of this task disputed and nobody has ruled on still stands
        # against this one's checks: it is told, and the rule sees it (state.slice_history).
        settled = rulings.ruled(events, rulings.KEPT)
        theirs = {
            check: reason
            for check, (by, reason) in _disputes(events, task.id).items()
            if by != worker and check in mine - settled - state.tasks[task.id].passing
        }
        if theirs:
            notes.append(predecessor_disputes_note(theirs))
        added = mine & {
            str(check)
            for e in events[since:]
            if e.event is EventType.APPROVED and e.actor == "investor"
            for check in e.data.get("added_checks", ())
        }
        if added and history:  # a worker that has not worked yet gets them in its first brief
            notes.append(added_checks_note(self.sheet, added, self.paths.checks))
        if resume:
            prompt = continuation_prompt(
                self.run_gate(task, worker),
                disputed - theirs.keys(),
                history[-1].denied_tools,
                task.paths[0],
                notes,
                _last_denial_reasons(events, worker),
            )
        else:
            # A new session starts from the first brief; what the investor ruled still applies.
            prompt = "\n\n".join([self._first_prompt(task, worker, state), *notes])
        spec = SliceSpec(
            session_id=uuid.UUID(session),
            resume=resume,
            prompt=prompt,
            model=self.config.model,
            cap_micros=cap,
            append_system_prompt=self._builder_prompt(),
            thinking_tokens=self.config.thinking_tokens,
        )
        number = ws.slices + 1
        start = {"slice": number, "task": task.id, "cap_micros": cap, "session": session}
        return _Pending(
            task, worker, number, spec, start, ws.session_total_micros, ws.session_total_tokens
        )

    def _status_line(self, task: Task, worker: str, number: int, round_n: int) -> None:
        events = self.events()
        passing = slice_history(events)[worker][-1].passing
        spent = budget.round_spend(events, round_n).cost_micros
        of = budget.round_budget(self.sheet, events, round_n)
        self.say(
            f"{worker} slice {number} on {task.id}: {len(passing)}/{len(self.checks_of(task))} "
            f"checks pass; round {round_n} has spent ${usd(spent)} of ${usd(of)}"
        )

    def _gate_slice(self, task: Task, worker: str, record: Recorder, status: object = None) -> None:
        """Gate the worker's last slice and record what it disputes, unless that is already on
        the ledger. `status` is the worker's raw report; after an interruption it is gone, so
        only the gate's results are recovered and the worker may raise its disputes again."""
        events = self.events()
        history = slice_history(events).get(worker, [])
        if not history or history[-1].outcome in INFRASTRUCTURE:
            return
        number = history[-1].slice
        graded = {e.data.get("check") for e in events if _gated(e, worker, number)}
        if {c.id for c in self.checks_of(task)} <= graded:
            return
        # A run killed between two results leaves the slice half graded: grade the rest.
        results = [r for r in self.run_gate(task, worker) if r.check_id not in graded]
        for r in results:
            data: dict[str, Any] = {"check": r.check_id, "task": task.id, "status": str(r.status)}
            data |= {
                "detail": r.detail,
                "worker": worker,
                "slice": number,
                "sandboxed": r.sandboxed,
            }
            record("gate", EventType.CHECK_RESULT, data=data)
        # Only a check of this task that fails right now can be disputed, once, and never one
        # the investor has ruled on.
        raised = frozenset().union(*(r.disputed for r in history))
        settled = rulings.ruled(events, rulings.KEPT)
        failing = {r.check_id for r in results if not r.passed}
        open_to_dispute = failing - raised - settled
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
        since = _after_last_slice(events, worker)
        raised = frozenset().union(*(r.disputed for r in history))
        open_disputes = sorted((needed & raised) - history[-1].passing)  # a passing one is moot
        if open_disputes and any(_rules_on_a_check(e, task.id) for e in events[since:]):
            # The investor was part way through this worker's disputes when the run stopped.
            # The rest are asked before anything else is decided: a kept check no longer makes
            # the rule escalate, so the rule alone would leave them unasked.
            self._ask_disputes(task, worker, open_disputes, events, record)
            return None
        verdict = decide(needed, history, self.config.policy)
        if verdict.decision is Decision.RETRY:
            return self._infrastructure(run, history, record) if run else None
        if verdict.decision is Decision.ESCALATE:
            # A dispute is asked about for as long as the verdict still lists it: each ruling
            # removes one, so an escalation interrupted half way is finished on the next pass.
            # A block is settled by one answer.
            if verdict.reason == "disputed" or not any(
                _unblocks(e, task.id) for e in events[since:]
            ):
                self._escalate(task, worker, verdict, events, since, record)
        elif verdict.decision is Decision.FIRE and (
            self.config.firing or verdict.reason == "slice limit"
        ):
            data: dict[str, Any] = {"worker": worker, "task": task.id, "reason": verdict.reason}
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
            self._ask_disputes(task, worker, verdict.evidence["disputed"], events, record)
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

    def _ask_disputes(
        self,
        task: Task,
        worker: str,
        checks: Sequence[str],
        events: Sequence[Event],
        record: Recorder,
    ) -> None:
        """Ask the investor to rule on each disputed check. The first one left unruled sets the
        task aside."""
        described = {c.id: c.description for c in self.sheet.checks}
        raised = _disputes(events, task.id)
        for check in checks:
            by, reason = raised.get(check, (worker, ""))  # a fired worker's dispute is put too
            advice = self.advise(check, reason) if self.advise else None
            if advice:
                self.say(advice)
            ruling = rulings.ask_dispute(
                self.ask,
                task=task.id,
                worker=by,
                check=check,
                description=safe_text(" ".join(described.get(check, "").split()), limit=200),
                reason=reason,
            )
            if ruling is None:
                self.say(f"Task {task.id} is set aside: {by} disputes {check}.")
                record("boss", EventType.ABANDONED, data={"task": task.id, "reason": "disputed"})
                return
            ruled = {"task": task.id, "worker": by, "check": check, "ruling": ruling}
            record("investor", EventType.RULED, data=ruled)

    def _infrastructure(self, run: SliceRun, history: list[Any], record: Recorder) -> str | None:
        attempt = 0
        for r in reversed(history):
            # A lost session is retried on its own count: it says nothing of a provider's health.
            lost = Outcome.SESSION_LOST
            if r.outcome not in INFRASTRUCTURE or (r.outcome is lost) != (run.outcome is lost):
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


def _last_slice(events: Sequence[Event]) -> int:
    """Index of the last `slice_end`, or -1 when no slice has ended."""
    return max((i for i, e in enumerate(events) if e.event is EventType.SLICE_END), default=-1)


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


def _last_denial_reasons(events: Sequence[Event], worker: str) -> list[dict[str, str]]:
    """The reasons the CLI gave for the refused calls of the worker's last slice, as recorded."""
    since = _after_last_slice(events, worker)
    raw = events[since - 1].data.get("denial_reasons") if since else None
    return [
        {"tool": str(r["tool"]), "reason": str(r["reason"])}
        for r in raw or ()
        if isinstance(r, dict) and "tool" in r and "reason" in r
    ]


def _disputes(events: Sequence[Event], task: str) -> dict[str, tuple[str, str]]:
    """Each check of the task a worker disputed, with who disputed it and why (the latest wins)."""
    return {
        str(e.data["check"]): (str(e.data.get("worker", "")), str(e.data.get("reason", "")))
        for e in events
        if e.event is EventType.DISPUTED and e.data.get("task") == task and "check" in e.data
    }


def _gated(event: Event, worker: str, number: int) -> bool:
    data = event.data
    found = event.event is EventType.CHECK_RESULT
    return found and data.get("worker") == worker and data.get("slice") == number


def _rules_on_a_check(event: Event, task: str) -> bool:
    """Whether this is the investor's ruling on a disputed check of the task."""
    ruling = event.event is EventType.RULED and event.actor == "investor"
    return ruling and event.data.get("task") == task and "check" in event.data


def _unblocks(event: Event, task: str) -> bool:
    """Whether the investor has already answered this task's block."""
    return (
        event.event is EventType.RULED
        and event.actor == "investor"
        and event.data.get("ruling") == rulings.UNBLOCKED
        and event.data.get("task") == task
    )


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
    cancel: threading.Event | None = None,
    advise: Advise | None = None,
) -> FirmReport:
    events = paths.events()
    require_approval(events, sheet, paths.checks, paths.held_out, paths.investor_key, paths.rules)
    try:
        held_out_store.load(paths.held_out)  # approved files are hashed; an unreadable list is not
    except held_out_store.HeldOutError as exc:
        raise NotApprovedError(f"the held-out checks cannot be read: {exc}") from exc
    cfg = config or started_config(events) or FirmConfig()
    if started_config(events) is None:
        start = Event(run=run_id, round=0, actor="boss", event=EventType.STARTED)
        ledger.append(dataclasses.replace(start, data={"config": config_data(cfg)}))
    firm = _Firm(
        sheet,
        paths,
        ledger,
        run_id,
        env,
        cfg,
        ask,
        say,
        slice_runner,
        gate,
        sleep,
        clock,
        clock(),
        cancel or threading.Event(),
        advise,
    )
    return firm.run()
