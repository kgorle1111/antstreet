"""Randomized simulation of the firm loop: random term sheets, configs and worker behaviour, seven
invariants checked over thousands of seeded scenarios. No model calls, no pytest gate: the gate is
a pure function of the files in a workspace.

How a scenario runs. A scenario is a seed. It fixes a term sheet (1-3 tasks, 1-4 checks each, 1-3
rounds), a `FirmConfig`, the investor's answers for later rounds, and an endless script of worker
behaviour: script position `i` is drawn from `Random(seed, i)`, so it never depends on the run. A
simulated worker consumes one position per call; the fake gate reads `<task>.py` in the workspace,
a JSON list of the check ids that file "makes pass".

Crash-resume equivalence (invariant 5), precisely. Interrupt the run by raising `KeyboardInterrupt`
from the worker, before it does any work, at a random script position, then call `run_firm` again
with a fresh worker object that continues the same script. The interrupted call recorded a
`slice_start` and no `slice_end` (an orphan). The two runs are "the same" when

  * their ledgers, after dropping orphaned `slice_start` events and the fields that are not part of
    the run's meaning (timestamps, run id, session uuids renamed in order of appearance, log
    paths), are the same sequence of (round, actor, event, cost, tokens, billing, data);
  * the workers were briefed the same way: same prompt, cap and resume flag for every finished
    slice, in order, and the same true cost;
  * the reports are the same, and so are the product and every workspace, byte for byte.

An orphaned `slice_start` still counts toward `RunLimits.max_slices`, so a run whose slice limit
binds is not equivalent (see `test_an_orphaned_slice_start_uses_up_the_slice_limit`); those
scenarios are excluded from the equivalence test and nothing else is.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from boss import budget as budget_mod
from boss.approval import content_hashes
from boss.errors import INFRASTRUCTURE, Outcome
from boss.firm import FirmConfig, FirmReport, run_firm
from boss.gate import Check, CheckResult, CheckStatus
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.limits import RunLimits
from boss.report import build_report, render_report
from boss.rule import FiringPolicy
from boss.rundir import RunPaths
from boss.runner import SliceRun
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, Task, TermSheet, structural_problems
from boss.worker import IsolationError

ENV = {"HOME": "/h"}
TOOLS = ("Read", "Write", "Edit", "Bash", "WebFetch")
MIN_CAP = budget_mod.MIN_SLICE_MICROS


@pytest.fixture(autouse=True)
def _no_fsync(monkeypatch):
    # The ledger fsyncs every line; that is what makes it crash-safe and what makes thousands of
    # simulated runs slow. Nothing here needs the durability, only the ledger's contents.
    monkeypatch.setattr(os, "fsync", lambda fd: None)


# ---------------------------------------------------------------------------------------------
# Scenarios


@dataclass(frozen=True)
class Scenario:
    seed: int
    sheet: TermSheet
    config: FirmConfig
    answers: tuple[str, ...]
    ki_rate: float  # chance that a script position raises KeyboardInterrupt
    iso_rate: float  # ... IsolationError
    tick: tuple[float, ...]  # what one call of the fake clock may advance it by
    script: tuple[Behaviour, ...] | None = None  # hand-written behaviour, then `IDLE` for ever
    mode: str = "normal"  # "cheap": free stalling slices; "hostile": mostly infrastructure failures

    @property
    def n_checks(self) -> int:
        return len(self.sheet.checks)

    def checks_of(self, task_id: str) -> list[str]:
        return [c.id for c in self.sheet.checks if c.task == task_id]


def make_scenario(
    seed: int, *, ki_rate: float = 0.0, iso_rate: float = 0.0, max_seconds: bool = True
) -> Scenario:
    rng = random.Random(seed)
    n_tasks = rng.randint(1, 3)
    checks: list[CheckSpec] = []
    tasks: list[Task] = []
    for t in range(1, n_tasks + 1):
        tasks.append(Task(f"t{t}", f"Create t{t}.py.", (f"t{t}.py",)))
        for _ in range(rng.randint(1, 4)):
            n = len(checks) + 1
            checks.append(CheckSpec(f"c{n:02d}", f"check {n}", f"test_c{n:02d}.py", f"t{t}"))
    n_rounds = rng.randint(1, 3)
    unlocks: list[int] = []
    for _ in range(n_rounds - 1):
        unlocks.append(rng.randint(max([1, *unlocks]), len(checks)))
    unlocks.append(len(checks))
    rounds = []
    for k in range(1, n_rounds + 1):
        low, high = rng.choice([(90_000, 130_000), (130_000, 350_000), (350_000, 900_000),
                                (350_000, 900_000), (900_000, 2_000_000),
                                (900_000, 2_000_000)])  # fmt: skip
        rounds.append(Round(k, rng.randint(low, high), unlocks[k - 1]))
    sheet = TermSheet(
        "Build things.",
        sum(r.budget_micros for r in rounds),
        tuple(rounds),
        tuple(checks),
        tuple(tasks),
        True,
    )
    limits = RunLimits(
        max_slices=rng.choice([1, 2, 3, 5, 8, 12, 20, 60, 60, 60, 60, 60]),
        max_workers=rng.choice([1, 2, 3, 4, 6, 16, 16, 16, 16]),
        max_seconds=(rng.choice([15.0, 90.0, 400.0, 3000.0]) if max_seconds and rng.random() < 0.15
                     else None),
    )  # fmt: skip
    config = FirmConfig(
        slice_micros=rng.choice([3_000, 10_000, 50_000, 100_000, 100_000, 200_000, 400_000]),
        reserve_micros=rng.choice([0, 5_000, 50_000, 100_000, 100_000, 100_000, 150_000]),
        policy=FiringPolicy(stall_slices=rng.randint(1, 4), max_slices=rng.randint(1, 6)),
        firing=rng.random() < 0.8,
        limits=limits,
    )
    answers = tuple(
        rng.choices(
            ["y", "yes", "a", "approve", "n", "no", "EOF", "", "maybe"],
            weights=[12, 4, 2, 2, 2, 1, 1, 1, 1],
        )[0]
        for _ in range(n_rounds - 1)
    )
    mode = rng.choices(["normal", "cheap", "hostile"], weights=[70, 15, 15])[0]
    ticks = (0.0, 0.0, 1.0, 2.0, 10.0, 60.0)
    return Scenario(seed, sheet, config, answers, ki_rate, iso_rate, ticks, None, mode)


@dataclass(frozen=True)
class Behaviour:
    exc: str | None
    outcome: Outcome
    progress: str
    n_new: int
    sub: int  # seed for the choices that need the workspace (which checks, which tool)
    status: str
    cost_kind: str
    cost_frac: float
    disputes: str
    denied: tuple[str, ...]
    exact: int | None = None  # the slice's true cost, overriding cost_kind and cost_frac


def beh(**kw: Any) -> Behaviour:
    """A hand-written behaviour: a completed slice that touches nothing and costs half its cap."""
    base: dict[str, Any] = dict(
        exc=None, outcome=Outcome.COMPLETED, progress="untouched", n_new=1, sub=0,
        status="continuing", cost_kind="within", cost_frac=0.5, disputes="none", denied=(),
    )  # fmt: skip
    return Behaviour(**(base | kw))


IDLE = beh()


def behaviour(scn: Scenario, pos: int) -> Behaviour:
    if scn.script is not None:
        return scn.script[pos] if pos < len(scn.script) else IDLE
    rng = random.Random(scn.seed * 1_000_003 + pos)
    roll = rng.random()
    exc = (
        "interrupt"
        if roll < scn.ki_rate
        else "isolation"
        if roll < scn.ki_rate + scn.iso_rate
        else None
    )
    outcome = rng.choices(
        list(Outcome),
        weights=[62, 12, 4, 3, 4, 3, 1, 5, 1, 5],  # in enum order: completed ... api_error
    )[0]
    weights = [46, 12, 16, 8, 3, 8, 7]
    if scn.mode == "cheap":  # nothing but the firing rule and the limits can stop a stalling worker
        outcome, weights = Outcome.COMPLETED, [4, 0, 55, 0, 0, 0, 41]
    elif scn.mode == "hostile" and rng.random() < 0.75:
        outcome = rng.choice([Outcome.RATE_LIMITED, Outcome.API_ERROR])
    return Behaviour(
        exc=exc,
        outcome=outcome,
        progress=rng.choices(
            ["progress", "all", "stall", "regress", "wipe", "adopt", "untouched"],
            weights=weights,
        )[0],
        n_new=rng.randint(1, 3),
        sub=rng.getrandbits(32),
        status=rng.choices(
            ["done", "continuing", "blocked", "garbage", "missing"], weights=[22, 40, 10, 8, 20]
        )[0],
        cost_kind="zero"
        if scn.mode != "normal"
        else rng.choices(
            ["within", "overshoot", "far", "zero", "unknown"], weights=[45, 18, 5, 8, 20]
        )[0],
        cost_frac=rng.random(),
        disputes=rng.choices(
            ["none", "valid", "passing", "other", "malformed"], weights=[70, 12, 6, 5, 7]
        )[0],
        denied=tuple(rng.sample(TOOLS, rng.choice([0, 0, 0, 1, 1, 2]))),
    )


# ---------------------------------------------------------------------------------------------
# The simulated world: worker, session store, fake gate, clock


@dataclass
class Call:
    invocation: int
    actor: str
    task: str
    number: int
    round: int
    cap: int
    resume: bool
    session: str
    prompt: str
    returned: bool = False  # False: raised (interrupt, isolation) before the loop recorded an end
    outcome: Outcome | None = None
    true_cost: int = 0
    reported: int | None = None
    pos: int | None = None


@dataclass
class Tamper:
    """Edit a check file the `index`-th time `where` ("worker", "gate", "clock") is called."""

    where: str
    index: int
    path: Path
    done: bool = False
    at_line: int = -1  # ledger lines written when the edit was made
    original: str = ""


class CrashingLedger(LedgerWriter):
    """A ledger writer that dies (KeyboardInterrupt) just before chosen appends: the event is lost,
    and whatever the loop did before it (files, workspaces) stays."""

    def __init__(self, path: Path, world: World):
        super().__init__(path)
        self.world = world

    def append(self, event: Event) -> None:
        w = self.world
        if not (event.event is EventType.APPROVED and event.round == 0):  # the harness's own
            w.appends += 1
            w.appended[event.event] += 1
            due = w.crash_before and w.crash_before[0] == w.appends
            typed = (event.event, w.appended[event.event]) in w.crash_on
            if due or typed:
                if due:
                    w.crash_before.pop(0)
                else:
                    w.crash_on.remove((event.event, w.appended[event.event]))
                w.crashed_on.append(event.event)
                raise KeyboardInterrupt
        super().append(event)


class World:
    def __init__(self, scn: Scenario, paths: RunPaths, interrupts: list[tuple[int, bool]]):
        self.scn, self.paths = scn, paths
        self.pos = 0  # next script position
        self.invocations = 0
        self.interrupted = 0  # calls that raised KeyboardInterrupt
        self.calls: list[Call] = []
        self.sessions: dict[str, int] = {}  # the CLI's session store: session -> cumulative cost
        self.violations: list[str] = []
        self.interrupts = sorted(interrupts)  # (script position, late)
        self.tamper: Tamper | None = None
        self.counts: Counter[str] = Counter()
        self.sleeps: list[float] = []
        self.marks: dict[str, list[int]] = {}  # ledger lines at each worker/gate/clock call
        self.gate_interrupt: int | None = None  # raise KeyboardInterrupt in the n-th gate call
        self.appends = 0  # ledger appends attempted, across resumes
        self.crash_before: list[int] = []  # raise KeyboardInterrupt instead of the n-th append
        self.crash_on: list[tuple[EventType, int]] = []  # ... or the n-th append of a type
        self.appended: Counter[EventType] = Counter()
        self.strict_sessions = True
        self.crashed_on: list[EventType] = []
        # A worker is called at most this often: see `call_bound`.
        self.bound = call_bound(scn)

    def fire_tamper(self, where: str) -> None:
        self.counts[where] += 1
        lines = self.paths.ledger.read_bytes().count(b"\n")
        self.marks.setdefault(where, []).append(lines)
        t = self.tamper
        if t and not t.done and t.where == where and t.index == self.counts[where]:
            t.done, t.at_line, t.original = True, lines, t.path.read_text()
            t.path.write_text("def test_anything():\n    pass\n")

    # -- the worker ---------------------------------------------------------------------------

    def worker(self, spec, workspace: Path, log_path: Path, *, env) -> SliceRun:
        self.invocations += 1
        self.fire_tamper("worker")
        start = read_events(self.paths.ledger)[-1]
        if start.event is not EventType.SLICE_START:
            self.violations.append(f"worker called after {start.event}, not a slice_start")
        actor, data = start.actor, start.data
        session = str(spec.session_id)
        call = Call(
            self.invocations, actor, data["task"], data["slice"], start.round,
            data["cap_micros"], spec.resume, session, spec.prompt,
        )  # fmt: skip
        self.calls.append(call)
        # Termination (invariant 1): the loop must never call the worker more often than the bound
        # derived from the configuration.
        if self.invocations - self.interrupted > self.bound or (
            self.invocations > self.scn.config.limits.max_slices
        ):
            raise AssertionError(
                f"worker called {self.invocations} times ({self.interrupted} interrupted); "
                f"bound {self.bound}, max_slices {self.scn.config.limits.max_slices}"
            )
        if spec.cap_micros != call.cap:
            self.violations.append(f"spec cap {spec.cap_micros} != slice_start cap {call.cap}")
        early = bool(self.interrupts) and self.interrupts[0] == (self.pos, False)
        late = bool(self.interrupts) and self.interrupts[0] == (self.pos, True)
        if early:
            self.interrupts.pop(0)
            self.interrupted += 1
            raise KeyboardInterrupt
        call.pos = self.pos
        beh = behaviour(self.scn, self.pos)
        self.pos += 1
        if late:
            self.interrupts.pop(0)
        if beh.exc == "isolation":
            raise IsolationError("simulated: hooks ran")
        if beh.exc == "interrupt":
            self.interrupted += 1
            raise KeyboardInterrupt
        run = self._work(beh, spec, call, workspace, log_path)
        if late:
            self.interrupted += 1
            raise KeyboardInterrupt  # after the slice spent its money and wrote its files
        call.returned = True
        return run

    def _work(self, beh: Behaviour, spec, call: Call, workspace: Path, log_path: Path) -> SliceRun:
        sheet, rng = self.scn.sheet, random.Random(beh.sub)
        # The session contract the loop relies on: a first slice creates the session, a later one
        # resumes it, and a slice that failed for infrastructure reasons created nothing.
        if self.strict_sessions and spec.resume and call.session not in self.sessions:
            self.violations.append(
                f"{call.actor} slice {call.number} resumed a session that does not exist"
            )
            return self._result(Outcome.CRASHED, None, None, None, [], log_path)
        if self.strict_sessions and not spec.resume and call.session in self.sessions:
            self.violations.append(f"{call.actor} slice {call.number} started an existing session")
            return self._result(Outcome.CRASHED, None, None, None, [], log_path)

        ids = self.scn.checks_of(call.task)
        target = workspace / f"{call.task}.py"
        current = _read_passing(target)
        previous = _read_passing(workspace / "previous_attempt" / f"{call.task}.py")
        after = _progress(beh, ids, current, previous, rng)
        if after is not None:
            target.write_text(json.dumps(sorted(after)))
        after = after if after is not None else current

        infra = beh.outcome in INFRASTRUCTURE
        cap, reserve = call.cap, self.scn.config.reserve_micros
        true = {
            "within": int(beh.cost_frac * cap),
            "overshoot": cap + int(beh.cost_frac * reserve),
            "far": cap + reserve + 1 + int(beh.cost_frac * 300_000),
            "zero": 0,
            "unknown": int(
                beh.cost_frac * cap
            ),  # crashed or killed: whatever it spent stays hidden
        }[beh.cost_kind]
        if beh.exact is not None:
            true = beh.exact
        if infra:
            true = 0
        call.outcome, call.true_cost = beh.outcome, true
        total_before = self.sessions.get(call.session, 0)
        reported: int | None = total_before + true
        if beh.cost_kind == "unknown" or (infra and beh.cost_frac < 0.5):
            reported = None
        call.reported = reported
        if not infra:
            self.sessions[call.session] = total_before + true
        status = _status(beh, sheet, call.task, self.scn, ids, after, rng)
        denials = [{"tool": tool, "reason": "rule"} for tool in beh.denied]
        return self._result(beh.outcome, reported, status, denials, [], log_path, rng)

    def _result(self, outcome, total, status, denials, _unused, log_path, rng=None) -> SliceRun:
        rate = None
        if outcome in (Outcome.USAGE_LIMIT, Outcome.RATE_LIMITED) and rng is not None:
            rate = rng.choice([None, {"resetsAt": 5000.0}, {"unifiedWindows": "junk"}])
        return SliceRun(
            outcome=outcome,
            usage=Usage(total, 10, 5, 0),
            status=status,
            session_id=None,
            exit_code=0,
            duration_s=0.1,
            log_path=log_path,
            denials=denials or [],
            rate_limit=rate,
        )

    # -- the fake gate ------------------------------------------------------------------------

    def gate(self, workspace: Path, checks_dir: Path, checks: list[Check]) -> list[CheckResult]:
        """A pure function of the workspace's files: check c passes iff `<task>.py` lists it."""
        self.counts["gate_calls"] += 1
        if self.gate_interrupt == self.counts["gate_calls"]:
            self.gate_interrupt = None
            self.interrupted += 1
            raise KeyboardInterrupt
        task_of = {c.id: c.task for c in self.scn.sheet.checks}
        results = []
        for check in checks:
            passing = _read_passing(workspace / f"{task_of[check.id]}.py")
            ok = check.id in passing
            status = CheckStatus.PASSED if ok else CheckStatus.FAILED
            results.append(
                CheckResult(check.id, status, 0 if ok else 1, "ok" if ok else "assertion failed",
                            "" if ok else f"E assert {check.id}", 0.0)
            )  # fmt: skip
        self.fire_tamper("gate")
        return results


def _read_passing(path: Path) -> set[str]:
    return set(json.loads(path.read_text())) if path.is_file() else set()


def _progress(
    beh: Behaviour, ids: list[str], current: set[str], previous: set[str], rng
) -> set[str] | None:
    """The check ids `<task>.py` makes pass after the slice, or None if the worker wrote nothing."""
    base = set(current)
    if beh.progress == "adopt":
        base = set(previous) | base
    missing = sorted(set(ids) - base)
    if beh.progress in ("progress", "adopt"):
        return base | set(rng.sample(missing, min(len(missing), beh.n_new)))
    if beh.progress == "all":
        return set(ids)
    if beh.progress == "regress":
        keep = [c for c in sorted(base) if rng.random() < 0.5]
        return set(keep)
    if beh.progress == "wipe":
        return set()
    if beh.progress == "stall":
        return base
    return None


_GARBAGE = (
    {"status": "banana", "reason": "??"},
    {"status": 7, "reason": None},
    {"reason": 5},
    {},
    {"status": "done", "reason": "x" * 5000},
    {"status": ["done"], "reason": "sk-ant-" + "k" * 40},
)


def _status(beh, sheet, task, scn, ids, after, rng) -> dict[str, Any] | None:
    if beh.status == "missing":
        return None
    if beh.status == "garbage":
        return dict(rng.choice(_GARBAGE))
    status: dict[str, Any] = {"status": beh.status, "reason": f"sim {beh.status}"}
    failing = sorted(set(ids) - after)
    others = [c.id for c in sheet.checks if c.task != task] + ["c99"]
    entry = lambda c, why="the idea says otherwise": {"check": c, "reason": why}  # noqa: E731
    if beh.disputes == "valid" and failing:
        status["disputed_checks"] = [
            entry(c) for c in rng.sample(failing, rng.randint(1, len(failing)))
        ]
    elif beh.disputes == "passing" and after:
        status["disputed_checks"] = [entry(c) for c in sorted(after)]
    elif beh.disputes == "other":
        status["disputed_checks"] = [entry(rng.choice(others))]
    elif beh.disputes == "malformed":
        first = failing[0] if failing else ids[0]
        status["disputed_checks"] = rng.choice(
            [
                {"check": first, "reason": "not a list"},
                "c01",
                [None, 5, "c01", [first]],
                [{"check": first}],
                [{"check": first, "reason": ""}],
                [{"check": first, "reason": "   "}],
                [{"check": 5, "reason": "why"}],
                [{"check": first, "reason": 7}],
                [entry(first), entry(first, "again")],
                [entry(first, "y" * 10_000)],
                [entry(first, "\x1b[31m sk-ant-" + "z" * 40)],
            ]
        )
    return status


class Clock:
    """A fake monotonic clock: each reading advances it by a step drawn from the scenario."""

    def __init__(self, scn: Scenario):
        self.t, self.calls, self.rng, self.steps = (
            1000.0,
            0,
            random.Random(scn.seed ^ 0xC10C),
            scn.tick,
        )
        self.world: World | None = None

    def __call__(self) -> float:
        self.calls += 1
        if self.world and self.calls > 500 + 4 * self.world.invocations:
            raise AssertionError("the loop reads the clock for ever without calling the worker")
        if self.world:
            self.world.fire_tamper("clock")
        value = self.t
        self.t += self.rng.choice(self.steps)
        return value


def call_bound(scn: Scenario) -> int:
    """Most worker calls the configuration allows, excluding calls that raised KeyboardInterrupt.

    A worker's counted (non-infrastructure) slices stop at `policy.max_slices`: `decide` fires it
    right after its P-th counted slice, and a fired worker is never funded again. Each counted slice
    can be preceded by at most 4 infrastructure retries (the 5th consecutive failure gives up the
    run), and a trailing streak adds at most 5 more before the run ends, so one worker gets at most
    5*P calls. A task gets at most 2 workers (the hire and one reassignment) and the run at most
    `limits.max_workers`. Every call also records a `slice_start`, so `limits.max_slices` bounds the
    calls including the interrupted ones, which the worker checks separately.
    """
    workers = min(2 * len(scn.sheet.tasks), scn.config.limits.max_workers)
    return 5 * scn.config.policy.max_slices * workers


# ---------------------------------------------------------------------------------------------
# Running a scenario


@dataclass
class Result:
    scn: Scenario
    events: list[Event]
    report: FirmReport | None
    exc: BaseException | None
    world: World
    said: list[str]
    asked: list[str]
    product: dict[str, bytes]
    workspaces: dict[str, bytes]
    invocations_of_run_firm: int
    raw_ledger: str = ""
    events_before_rerun: int = 0
    calls_before_rerun: int = 0
    tamper: Tamper | None = None


def _tree(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def run_scenario(
    scn: Scenario,
    root: Path,
    *,
    interrupts: list[tuple[int, bool]] = (),
    resume: bool = True,
    max_resumes: int = 8,
    tamper: Tamper | None = None,
    gate_interrupt: int | None = None,
    crash_before: list[int] = (),
    crash_on: list[tuple[EventType, int]] = (),
    strict_sessions: bool = True,
    rerun: bool = False,
) -> Result:
    """Run `scn` in `root`. A KeyboardInterrupt is followed by another `run_firm` call, like a user
    re-running the command, up to `max_resumes` times."""
    paths = RunPaths(root / "run")
    paths.checks.mkdir(parents=True)
    for c in scn.sheet.checks:
        (paths.checks / c.file).write_text(f"def test_{c.id}():\n    assert True  # {c.id}\n")
    world = World(scn, paths, list(interrupts))
    world.gate_interrupt = gate_interrupt
    world.crash_before = sorted(crash_before)
    world.crash_on = list(crash_on)
    world.strict_sessions = strict_sessions
    if tamper is not None:
        tamper.path = paths.checks / tamper.path.name
    world.tamper = tamper
    clock = Clock(scn)
    clock.world = world
    said: list[str] = []
    asked: list[str] = []

    def ask(question: str) -> str:
        # The investor gives the same answer to the same question, however often it is asked.
        asked.append(question)
        n = int(question.split(":")[0].removeprefix("Round "))
        reply = scn.answers[n - 2] if 2 <= n <= len(scn.answers) + 1 else "EOF"
        if reply == "EOF":
            raise EOFError
        return reply

    report, exc, calls = None, None, 0
    before_events = before_calls = 0
    reran = False
    while True:
        calls += 1
        try:
            with CrashingLedger(paths.ledger, world) as ledger:
                if paths.ledger.stat().st_size == 0:
                    data = {"hashes": content_hashes(scn.sheet, paths.checks)}
                    ledger.append(Event("r1", 0, "investor", EventType.APPROVED, data=data))
                report = run_firm(
                    scn.sheet, paths, ledger, "r1", env=ENV, config=scn.config, ask=ask,
                    say=said.append, slice_runner=world.worker, gate=world.gate,
                    sleep=world.sleeps.append, clock=clock,
                )  # fmt: skip
            if rerun and not reran:
                reran = True
                # Run the finished run again, as a user would, with the edited check restored.
                before_events, before_calls = len(read_events(paths.ledger)), world.invocations
                if tamper and tamper.done:
                    tamper.path.write_text(tamper.original)
                continue
            break
        except KeyboardInterrupt as e:
            if not resume or calls > max_resumes:
                exc = e
                break
        except Exception as e:  # expected ones are asserted on; an unexpected one is a finding
            exc = e
            break
    return Result(
        scn, read_events(paths.ledger), report, exc, world, said, asked,
        _tree(paths.product), _tree(paths.root / "workspaces"), calls,
        paths.ledger.read_text(), before_events, before_calls, tamper,
    )  # fmt: skip


def run_in_tmp(scn: Scenario, **kw: Any) -> Result:
    with tempfile.TemporaryDirectory(prefix="boss_sim_") as d:
        return run_scenario(scn, Path(d), **kw)


# ---------------------------------------------------------------------------------------------
# Independent recomputations from the documented ledger contract (never `state.run_state`)


def independent_passed(events: list[Event], sheet: TermSheet) -> int:
    """Checks passing at the end: per task, the gate results of the best worker's latest gated
    slice, where the best worker is the one with most passing checks and later hires win ties."""
    hired: dict[str, list[str]] = {}
    for e in events:
        if e.event is EventType.HIRED:
            hired.setdefault(e.data["task"], []).append(e.data["worker"])
    results: dict[tuple[str, int], set[str]] = {}
    for e in events:
        if e.event is EventType.CHECK_RESULT:
            bucket = results.setdefault((e.data["worker"], e.data["slice"]), set())
            if e.data["status"] == "passed":
                bucket.add(e.data["check"])
    total = 0
    for task in sheet.tasks:
        own = {c.id for c in sheet.checks if c.task == task.id}
        latest = []
        for worker in hired.get(task.id, []):
            slices = [s for (w, s) in results if w == worker]
            latest.append(results[(worker, max(slices))] & own if slices else set())
        if latest:
            total += max(len(p) for p in latest)
    return total


def spent_by_round(
    events: list[Event], sheet: TermSheet, upto: int | None = None
) -> dict[int, int]:
    """Per round: known costs plus, for every slice that ended with an unknown cost and was not an
    infrastructure failure, the cap it was started with."""
    caps: dict[tuple[str, Any], int] = {}
    spent: dict[int, int] = {r.n: 0 for r in sheet.rounds}
    for e in events[: upto if upto is not None else len(events)]:
        if e.round < 1:
            continue
        if e.event is EventType.SLICE_START:
            caps[(e.actor, e.data["slice"])] = e.data["cap_micros"]
        if e.cost_micros is not None:
            spent[e.round] += e.cost_micros
        elif e.event is EventType.SLICE_END and e.data["outcome"] not in {
            o.value for o in INFRASTRUCTURE
        }:
            spent[e.round] += caps[(e.actor, e.data["slice"])]
    return spent


def _canon(events: list[Event]) -> list[tuple]:
    """The events that describe the run, without what is not part of its meaning (see the module
    docstring): timestamps, run id, session uuids and log paths; orphaned slice_starts."""
    sessions: dict[str, str] = {}
    pending: dict[str, int] = {}
    out: list[tuple | None] = []
    for e in events:
        data = dict(e.data)
        if e.event is EventType.HIRED:
            data["session"] = sessions.setdefault(data["session"], f"s{len(sessions) + 1}")
        if "log" in data:
            data["log"] = Path(data["log"]).name
        if e.event is EventType.SLICE_START:
            if e.actor in pending:
                out[pending[e.actor]] = None  # the earlier start never ended: orphaned
            pending[e.actor] = len(out)
        elif e.event is EventType.SLICE_END:
            pending.pop(e.actor, None)
        out.append(
            (e.round, e.actor, e.event.value, e.cost_micros, e.tokens_in, e.tokens_out,
             e.tokens_cached, e.billing.value, json.dumps(data, sort_keys=True))
        )  # fmt: skip
    for index in pending.values():
        out[index] = None
    return [x for x in out if x is not None]


def _briefing(result: Result) -> list[tuple]:
    """What each finished slice was given and what it truly cost."""
    sessions: dict[str, str] = {}
    rows = []
    for c in result.world.calls:
        if c.returned:
            session = sessions.setdefault(c.session, f"s{len(sessions)}")
            rows.append(
                (
                    c.actor,
                    c.number,
                    c.round,
                    c.cap,
                    c.resume,
                    session,
                    c.prompt,
                    c.outcome,
                    c.true_cost,
                )
            )
    return rows


# ---------------------------------------------------------------------------------------------
# The invariants, each a function over one finished scenario


def _fail(res: Result, message: str) -> None:
    raise AssertionError(f"seed {res.scn.seed}: {message}")


def check_termination(res: Result) -> None:
    w, cfg = res.world, res.scn.config
    if res.exc is not None and not isinstance(res.exc, IsolationError | KeyboardInterrupt):
        _fail(res, f"the loop raised {res.exc!r}")
    if res.exc is None and res.report is None:
        _fail(res, "no report and no exception")
    if w.invocations - w.interrupted > w.bound or w.invocations > cfg.limits.max_slices:
        _fail(
            res, f"{w.invocations} worker calls ({w.interrupted} interrupted) over bound {w.bound}"
        )
    if w.violations:
        _fail(res, f"worker protocol violated: {w.violations}")
    for seconds in w.sleeps:
        if not 2.5 <= seconds <= 120:
            _fail(res, f"backoff of {seconds}s outside the documented 2.5-120s")


def check_money(res: Result) -> None:
    ev, sheet, cfg = res.events, res.scn.sheet, res.scn.config
    reserve = cfg.reserve_micros
    budgets = {r.n: r.budget_micros for r in sheet.rounds}
    for i, e in enumerate(ev):
        if e.event is not EventType.SLICE_START:
            continue
        cap = e.data["cap_micros"]
        if not MIN_CAP <= cap <= cfg.slice_micros:
            _fail(res, f"slice started with cap {cap}, outside [{MIN_CAP}, {cfg.slice_micros}]")
        left = budgets[e.round] - spent_by_round(ev, sheet, i)[e.round]
        if left < cap + reserve:
            _fail(
                res, f"round {e.round}: slice cap {cap} started with {left} left, reserve {reserve}"
            )
    # Pair every slice the loop recorded with the simulated call that produced it.
    returned = [c for c in res.world.calls if c.returned]
    ends = [e for e in ev if e.event is EventType.SLICE_END]
    if len(returned) != len(ends):
        _fail(res, f"{len(returned)} finished calls but {len(ends)} slice_end events")
    beyond = {r: 0 for r in budgets}  # per round, largest overshoot past cap + reserve
    truth = {r: 0 for r in budgets}
    absorbed = {r: 0 for r in budgets}
    known: dict[str, int] = {}
    for call, end in zip(returned, ends, strict=True):
        if (call.actor, call.number) != (end.actor, end.data["slice"]):
            _fail(
                res, f"call {call.actor}#{call.number} recorded as {end.actor}#{end.data['slice']}"
            )
        if end.cost_micros is not None:
            gap = (
                end.cost_micros - call.true_cost
            )  # spend of earlier unknown-cost slices, folded in
            if gap < 0:
                _fail(res, f"ledger cost {end.cost_micros} below true cost {call.true_cost}")
            absorbed[call.round] = max(absorbed[call.round], gap)
            known[call.session] = known.get(call.session, 0) + end.cost_micros
    for c in res.world.calls:
        truth[c.round] += c.true_cost
        beyond[c.round] = max(beyond[c.round], c.true_cost - c.cap - reserve)
    for n, spent in spent_by_round(ev, sheet).items():
        # Only what the scenario itself overshot by beyond the reserve, and what the ledger charges
        # twice (a later slice's cost delta contains the spend of an earlier unknown-cost slice
        # that was already charged at its cap; see test_an_unknown_cost_slice_is_charged_twice),
        # may take a round past its budget.
        if spent > budgets[n] + beyond[n] + absorbed[n]:
            _fail(
                res,
                f"round {n} spent {spent}/{budgets[n]} (beyond {beyond[n]}, twice {absorbed[n]})",
            )
        if truth[n] > budgets[n] + max(beyond[n], 0):
            _fail(res, f"round {n} truly spent {truth[n]} of {budgets[n]} (beyond {beyond[n]})")
    for session, total in known.items():
        last = [c.reported for c in returned if c.session == session and c.reported is not None]
        if last and total != last[-1]:
            _fail(res, f"session ledger costs sum to {total}, the CLI reported {last[-1]}")


def check_passes(res: Result) -> None:
    if res.report is None:
        return
    ev, sheet = res.events, res.scn.sheet
    expected = independent_passed(ev, sheet)
    if (res.report.passed, res.report.total) != (expected, len(sheet.checks)):
        _fail(res, f"report {res.report.passed}/{res.report.total}, ledger says {expected}")
    for i, e in enumerate(ev):
        if e.event is EventType.ROUND_CLOSED and e.data["passed"] != independent_passed(
            ev[:i], sheet
        ):
            _fail(res, f"round {e.round} closed with passed={e.data['passed']}")
    gated = {e.data["check"] for e in ev
             if e.event is EventType.CHECK_RESULT and e.data["status"] == "passed"}  # fmt: skip
    if res.report.passed > len(gated):
        _fail(res, f"{res.report.passed} passes reported, the gate passed {len(gated)} checks")


def check_ledger(res: Result) -> None:
    ev, sheet, cfg = res.events, res.scn.sheet, res.scn.config
    checks_of = {t.id: {c.id for c in sheet.checks if c.task == t.id} for t in sheet.tasks}
    hired: dict[str, str] = {}
    per_task: Counter[str] = Counter()
    fired: set[str] = set()
    abandoned: set[str] = set()
    finished: dict[str, int] = Counter()
    opened: dict[str, int] = {}
    graded: dict[tuple[str, int], list[str]] = {}
    disputed: set[tuple[str, str]] = set()
    stopped = 0
    closed: dict[int, bool] = {}
    last_round = 0
    reassigned_to: str | None = None
    outcome_of: dict[tuple[str, int, str], str] = {}
    for i, e in enumerate(ev):
        d, actor = e.data, e.actor
        if (
            i
            and ev[i - 1].event is EventType.BLOCKED
            and not (e.event is EventType.ABANDONED and e.data["task"] == ev[i - 1].data["task"])
        ):
            _fail(res, "a blocked worker was not set aside at once")
        if stopped and not (
            e.event is EventType.ROUND_CLOSED and stopped == 1 and i == len(ev) - 1
        ):
            _fail(res, f"event {e.event} after stopped")
        if e.round < last_round:
            _fail(res, f"round went back from {last_round} to {e.round}")
        last_round = e.round
        if reassigned_to and not (e.event is EventType.HIRED and d["worker"] == reassigned_to):
            _fail(res, "reassigned is not followed by the hire it names")
        if e.event is not EventType.HIRED:
            reassigned_to = reassigned_to if e.event is EventType.REASSIGNED else None
        if e.event is EventType.HIRED:
            reassigned_to = None
            worker, task = d["worker"], d["task"]
            if worker in hired or worker != f"w{len(hired) + 1}" or task not in checks_of:
                _fail(res, f"bad hire {worker} for {task}")
            hired[worker] = task
            per_task[task] += 1
            if per_task[task] > 2:  # one hire plus one reassignment
                _fail(res, f"task {task} has {per_task[task]} workers")
        elif e.event is EventType.SLICE_START:
            worker = actor.removeprefix("worker:")
            if worker not in hired or hired[worker] != d["task"]:
                _fail(res, f"slice_start by {actor} on {d['task']}")
            if worker in fired:
                _fail(res, f"fired worker {worker} got slice {d['slice']}")
            if d["task"] in abandoned:
                _fail(res, f"abandoned task {d['task']} got a slice")
            if d["slice"] != finished[worker] + 1:
                _fail(res, f"{actor} started slice {d['slice']} after {finished[worker]} finished")
            if worker in opened and res.world.interrupted == 0:
                _fail(res, f"{actor} started a slice while another was open")
            opened[worker] = d["slice"]
        elif e.event is EventType.SLICE_END:
            worker = actor.removeprefix("worker:")
            if opened.pop(worker, None) != d["slice"]:
                _fail(res, f"{actor} slice_end {d['slice']} without its slice_start")
            finished[worker] += 1
        elif e.event is EventType.CHECK_RESULT:
            worker, number = d["worker"], d["slice"]
            if finished[worker] != number or hired.get(worker) != d["task"]:
                _fail(res, f"check_result for unfinished slice {worker}#{number}")
            if d["check"] not in checks_of[d["task"]]:
                _fail(res, f"check {d['check']} is not a check of {d['task']}")
            graded.setdefault((worker, number), []).append(d["check"])
            outcome_of[(worker, number, d["check"])] = d["status"]
        elif e.event is EventType.FIRED:
            worker = d["worker"]
            if hired.get(worker) != d["task"] or worker in fired:
                _fail(res, f"bad fired {worker}")
            fired.add(worker)
        elif e.event is EventType.REASSIGNED:
            if d["from"] not in fired or hired.get(d["from"]) != d["task"]:
                _fail(res, f"reassigned from {d['from']}, which was not fired on {d['task']}")
            reassigned_to = d["to"]
        elif e.event is EventType.ABANDONED:
            if d["task"] not in checks_of or d["task"] in abandoned:
                _fail(res, f"bad abandoned {d}")
            abandoned.add(d["task"])
        elif e.event is EventType.BLOCKED:
            if hired.get(actor.removeprefix("worker:")) != d["task"]:
                _fail(res, f"blocked by {actor} on {d['task']}")
        elif e.event is EventType.DISPUTED:
            worker, number = d["worker"], d["slice"]
            if actor != f"worker:{worker}" or hired.get(worker) != d["task"]:
                _fail(res, f"disputed by {actor} for {worker} on {d['task']}")
            if d["check"] not in checks_of.get(d["task"], ()) or (worker, d["check"]) in disputed:
                _fail(res, f"disputed {d['check']} is foreign or repeated")
            if finished[worker] != number:
                _fail(res, "disputed a slice that has not finished")
            if outcome_of.get((worker, number, d["check"])) in (None, "passed"):
                _fail(res, f"{d['check']} was disputed although it did not fail in that slice")
            disputed.add((worker, d["check"]))
        elif e.event is EventType.STOPPED:
            stopped += 1
        elif e.event is EventType.APPROVED and e.actor == "investor":
            n = d.get("round", 1)
            if n > 1 and closed.get(n - 1) is not True:
                _fail(res, f"round {n} funded although round {n - 1} did not unlock")
        elif e.event is EventType.ROUND_CLOSED:
            closed[e.round] = d["unlocked"]
        elif e.event is EventType.PAUSED and i != len(ev) - 2:
            _fail(res, "events after paused other than the round closing")
    for (worker, number), got in graded.items():
        if sorted(got) != sorted(checks_of[hired[worker]]):
            _fail(res, f"{worker}#{number} graded {got}")
    if len(hired) > cfg.limits.max_workers:
        _fail(res, f"{len(hired)} workers hired, limit {cfg.limits.max_workers}")
    starts = sum(e.event is EventType.SLICE_START for e in ev)
    if starts > cfg.limits.max_slices:
        _fail(res, f"{starts} slices started, limit {cfg.limits.max_slices}")
    render_report(build_report(ev))  # the board report must be able to read every ledger


# ---------------------------------------------------------------------------------------------
# Sweeps


N_SCENARIOS = 1200  # invariants 1-4 share one sweep, cached
_SWEEP: dict[int, Result] = {}


def sweep() -> list[Result]:
    for seed in range(N_SCENARIOS):
        if seed not in _SWEEP:
            _SWEEP[seed] = run_in_tmp(make_scenario(seed, ki_rate=0.02, iso_rate=0.01))
    return [_SWEEP[s] for s in range(N_SCENARIOS)]


def test_1_termination():
    for res in sweep():
        check_termination(res)


def test_2_money():
    for res in sweep():
        check_money(res)


def test_3_only_the_gate_grants_passes():
    for res in sweep():
        check_passes(res)


def test_4_ledger_is_well_formed():
    for res in sweep():
        check_ledger(res)


# ---------------------------------------------------------------------------------------------
# 5. Crash-resume equivalence


def slice_starts(res: Result) -> int:
    return sum(e.event is EventType.SLICE_START for e in res.events)


def equivalence_scenario(seed: int) -> Scenario:
    # The wall-clock limit is per invocation by design, so a resumed run gets a new allowance.
    return make_scenario(seed, ki_rate=0.0, iso_rate=0.01, max_seconds=False)


def check_equivalence(seed: int) -> str:
    scn = equivalence_scenario(seed)
    ref = run_in_tmp(scn)
    if ref.world.pos == 0:
        return "no slices"
    rng = random.Random(seed ^ 0x5EED)
    interrupts = sorted((rng.randrange(ref.world.pos), False) for _ in range(rng.randint(1, 3)))
    # An orphaned slice_start counts toward max_slices; that class is excluded and pinned by
    # test_an_orphaned_slice_start_uses_up_the_slice_limit.
    if slice_starts(ref) + len(interrupts) >= scn.config.limits.max_slices:
        return "slice limit binds"
    hit = run_in_tmp(scn, interrupts=interrupts)
    if hit.world.interrupted != len(interrupts):
        _fail(hit, f"{len(interrupts)} interruptions planned, {hit.world.interrupted} happened")
    same = [
        ("exception", type(ref.exc), type(hit.exc)),
        ("report", ref.report, hit.report),
        ("ledger", _canon(ref.events), _canon(hit.events)),
        ("briefings", _briefing(ref), _briefing(hit)),
        ("product", ref.product, hit.product),
        ("workspaces", ref.workspaces, hit.workspaces),
        ("questions", ref.asked, hit.asked),
        ("sleeps", len(ref.world.sleeps), len(hit.world.sleeps)),
    ]
    for name, a, b in same:
        if a != b:
            _fail(hit, f"interrupted at {interrupts}: {name} differs")
    return "checked"


def test_5_crash_resume_equivalence():
    seen: Counter[str] = Counter()
    for seed in range(700):
        seen[check_equivalence(seed)] += 1
    assert seen["checked"] > 350, seen  # the exclusions must stay the minority


# ---------------------------------------------------------------------------------------------
# 6. Determinism


def digest(res: Result) -> str:
    keep = [_canon(res.events), res.report, _briefing(res), sorted(res.product.items()),
            sorted(res.workspaces.items()), res.asked, len(res.world.sleeps)]  # fmt: skip
    return json.dumps(keep, sort_keys=True, default=repr)


def test_6_same_scenario_same_ledger():
    for seed in range(350):
        scn = make_scenario(seed, ki_rate=0.02, iso_rate=0.01)
        if digest(run_in_tmp(scn)) != digest(run_in_tmp(scn)):
            raise AssertionError(f"seed {seed}: two runs of one scenario differ")


_HASH_SEEDS = """
import hashlib, importlib.util, os, sys
os.fsync = lambda fd: None
spec = importlib.util.spec_from_file_location("sim", sys.argv[1])
sim = importlib.util.module_from_spec(spec)
sys.modules["sim"] = sim
spec.loader.exec_module(sim)
out = hashlib.sha256()
for seed in range(int(sys.argv[2])):
    res = sim.run_in_tmp(sim.make_scenario(seed, ki_rate=0.02, iso_rate=0.01))
    out.update(sim.digest(res).encode())
print(out.hexdigest())
"""


def test_6_no_dependence_on_the_process_hash_seed():
    # Set and dict ordering of strings changes between processes with PYTHONHASHSEED; the ledger
    # must not.
    digests = set()
    for hash_seed in ("1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        proc = subprocess.run(
            [sys.executable, "-c", _HASH_SEEDS, __file__, "60"],
            env=env, capture_output=True, text=True, check=True, timeout=120,
        )  # fmt: skip
        digests.add(proc.stdout.strip())
    assert len(digests) == 1, digests


# ---------------------------------------------------------------------------------------------
# 7. Approval


def tamper_run(seed: int) -> tuple[Result, Result, Tamper] | None:
    scn = make_scenario(seed, iso_rate=0.01)
    ref = run_in_tmp(scn)
    rng = random.Random(seed ^ 0x7A3)
    where = rng.choice(["worker", "clock"])
    if not ref.world.counts[where]:
        return None
    victim = rng.choice(scn.sheet.checks).file
    tamper = Tamper(where, rng.randint(1, ref.world.counts[where]), Path(victim))
    return ref, run_in_tmp(scn, tamper=tamper, rerun=True), tamper


def check_tamper(seed: int) -> str:
    made = tamper_run(seed)
    if made is None:
        return "no calls"
    ref, res, tamper = made
    if not tamper.done:
        _fail(res, "the edit was never made: the tampered run diverged before it")
    lines = res.raw_ledger.splitlines()
    ref_lines = ref.raw_ledger.splitlines()
    after = [Event.from_json(line) for line in lines[tamper.at_line : res.events_before_rerun]]
    forbidden = {EventType.CHECK_RESULT, EventType.SLICE_START}
    if tamper.where == "clock":
        forbidden |= {EventType.SLICE_END}
    bad = [e.event.value for e in after if e.event in forbidden]
    if bad:
        _fail(res, f"{tamper.where} #{tamper.index} edit at line {tamper.at_line}: then {bad}")
    ref_after = [Event.from_json(line).event for line in ref_lines[tamper.at_line :]]
    more_work = any(k in ref_after for k in (EventType.SLICE_START, EventType.CHECK_RESULT))
    ended = [e.event for e in after if e.event in (EventType.STOPPED, EventType.PAUSED)]
    if more_work and not ended and res.exc is None:
        _fail(res, f"{tamper.where} #{tamper.index}: the run went on to finish, unstopped")
    if any(e.event is EventType.STOPPED for e in res.events[: res.events_before_rerun]):
        if res.world.invocations != res.calls_before_rerun:
            _fail(res, "a worker was called when the run was resumed after the edit was undone")
        if len(res.events) != res.events_before_rerun:
            _fail(res, "a stopped run recorded events when it was resumed")
    return "checked"


def test_7_an_edited_check_stops_the_run():
    seen: Counter[str] = Counter()
    for seed in range(600):
        seen[check_tamper(seed)] += 1
    assert seen["checked"] > 450, seen


# ---------------------------------------------------------------------------------------------
# More of invariant 5: crashes anywhere a ledger line is written, and re-running a finished run


def safe_to_lose(prev: EventType | None, lost: EventType) -> bool:
    """Ledger writes whose loss the loop recovers from. Losing any other one is pinned by a
    regression test below: slice_end (test_a_crash_before_slice_end_*), check_result
    (test_a_slice_whose_gate_results_were_lost_*), disputed/fired/blocked/abandoned/paused/stopped
    after a slice (test_a_decision_lost_in_a_crash_*, the same cause), hired after reassigned
    (test_a_crash_between_reassigned_*), round_closed after stopped
    (test_a_crash_between_stopped_and_round_closed_*) or paused (test_a_paused_run_*)."""
    if lost in (EventType.SLICE_START, EventType.APPROVED):
        return True
    if lost is EventType.HIRED:
        return prev is not EventType.REASSIGNED
    if lost is EventType.ROUND_CLOSED:
        return prev not in (EventType.STOPPED, EventType.PAUSED)
    return lost is EventType.ABANDONED and prev is EventType.FIRED


def check_crash_equivalence(seed: int) -> str:
    scn = equivalence_scenario(seed)
    ref = run_in_tmp(scn)
    written = [e for e in ref.events if not (e.event is EventType.APPROVED and e.round == 0)]
    safe = [
        k
        for k in range(1, len(written) + 1)
        if safe_to_lose(written[k - 2].event if k >= 2 else None, written[k - 1].event)
    ]
    if not safe:
        return "nothing to lose"
    crashes = sorted(random.Random(seed).sample(safe, min(len(safe), 2)))
    # Each crash makes the loop write its lost line again, which shifts every later index by one.
    hit = run_in_tmp(scn, crash_before=[k + i for i, k in enumerate(crashes)])
    if hit.world.crashed_on != [written[k - 1].event for k in crashes]:
        _fail(hit, f"crashes planned at {crashes}, happened on {hit.world.crashed_on}")
    for name, a, b in [
        ("exception", type(ref.exc), type(hit.exc)),
        ("report", ref.report, hit.report),
        ("ledger", _canon(ref.events), _canon(hit.events)),
        ("briefings", _briefing(ref), _briefing(hit)),
        ("product", ref.product, hit.product),
        ("questions", sorted(set(ref.asked)), sorted(set(hit.asked))),
    ]:
        if a != b:
            _fail(hit, f"crash before appends {crashes} ({hit.world.crashed_on}): {name} differs")
    return "checked"


def test_5_crash_at_a_ledger_write_the_loop_recovers_from_is_invisible():
    seen: Counter[str] = Counter()
    for seed in range(700):
        seen[check_crash_equivalence(seed)] += 1
    assert seen["checked"] > 400, seen


def check_rerun(seed: int) -> str:
    res = run_in_tmp(make_scenario(seed), rerun=True)
    if res.exc is not None:
        _fail(res, f"re-running raised {res.exc!r}")
    first, added = res.events[: res.events_before_rerun], res.events[res.events_before_rerun :]
    kinds = {e.event for e in first}
    closed = [e for e in first if e.event is EventType.ROUND_CLOSED]
    if EventType.STOPPED in kinds:
        if added or res.world.invocations != res.calls_before_rerun:
            _fail(res, f"a stopped run went on when re-run: {[e.event.value for e in added]}")
        check_ledger(res)
        return "stopped"
    # Pinned by regression tests, each excluded here: a pause closes the round it interrupts
    # (test_a_paused_run_can_be_resumed); a round closed below its threshold, or a finished run,
    # asks the investor for the next round (test_re_running_a_run_*).
    if EventType.PAUSED in kinds:
        return "paused (excluded)"
    if closed and (not closed[-1].data["unlocked"] or res.report and res.report.all_passed):
        return "below threshold or finished (excluded)"
    # Every other run ends stopped, paused, finished or closed below a threshold; a round that
    # closed unlocked with work left is reachable only by a hand-made scenario.
    check_ledger(res)
    return "checked"


def test_4_re_running_a_finished_run_is_harmless():
    seen: Counter[str] = Counter()
    for seed in range(450):
        seen[check_rerun(seed)] += 1
    assert seen["stopped"] > 60, seen


# ---------------------------------------------------------------------------------------------
# The generator itself must reach the states the invariants are about


def test_the_generator_makes_valid_term_sheets():
    for seed in range(300):
        scn = make_scenario(seed)
        with tempfile.TemporaryDirectory() as d:
            checks = Path(d)
            for c in scn.sheet.checks:
                (checks / c.file).write_text(f"def test_{c.id}():\n    assert True\n")
            assert structural_problems(scn.sheet, checks) == [], seed


def test_the_generator_reaches_every_outcome_and_decision():
    seen: Counter[str] = Counter()
    for res in sweep():
        for e in res.events:
            seen[e.event.value] += 1
            if e.event is EventType.SLICE_END:
                seen["outcome:" + e.data["outcome"]] += 1
                seen["cost:" + ("unknown" if e.cost_micros is None else "known")] += 1
                seen["status:" + str((e.data["status"] or {}).get("status"))] += 1
        seen["exc:" + type(res.exc).__name__] += 1
        seen["rounds:" + str(len(res.scn.sheet.rounds))] += 1
        seen["report:" + str(res.report and res.report.stopped or "-")[:12]] += 1
    wanted = [e.value for e in EventType if e not in (EventType.BOSS_CALL, EventType.DENIED)]
    wanted.remove(EventType.TOPPED_UP.value)
    wanted += [f"outcome:{o.value}" for o in Outcome] + ["cost:unknown", "cost:known"]
    wanted += ["status:done", "status:continuing", "status:blocked", "status:none"]
    wanted += ["exc:IsolationError", "rounds:1", "rounds:2", "rounds:3"]
    wanted += [
        "report:round 1 clos",
        "report:investor dec",
        "report:paused: plan",
        "report:stopped: 2 s",
    ]
    missing = [w for w in wanted if not seen[w]]
    assert not missing, missing


# ---------------------------------------------------------------------------------------------
# Regression tests: what the simulation found. Each is a minimal hand-written scenario, strict
# xfail so that fixing the cause turns it into a failure that says to delete the marker.


def hand(
    script: list[Behaviour],
    *,
    budgets: tuple[int, ...] = (600_000,),
    unlocks: tuple[int, ...] | None = None,
    checks: tuple[int, ...] = (2,),
    slice_micros: int = 100_000,
    reserve: int = 100_000,
    policy: FiringPolicy | None = None,
    limits: RunLimits | None = None,
    answers: tuple[str, ...] = (),
) -> Scenario:
    tasks = [Task(f"t{t}", f"Create t{t}.py.", (f"t{t}.py",)) for t in range(1, len(checks) + 1)]
    specs = [
        CheckSpec(f"c{k:02d}", "check", f"test_c{k:02d}.py", f"t{t}")
        for k, t in enumerate((t for t, n in enumerate(checks, 1) for _ in range(n)), 1)
    ]
    unlocks = unlocks or (len(specs),) * len(budgets)
    rounds = tuple(Round(i, b, u) for i, (b, u) in enumerate(zip(budgets, unlocks, strict=True), 1))
    sheet = TermSheet("Build things.", sum(budgets), rounds, tuple(specs), tuple(tasks), True)
    config = FirmConfig(
        slice_micros=slice_micros, reserve_micros=reserve,
        policy=policy or FiringPolicy(), limits=limits or RunLimits(),
    )  # fmt: skip
    return Scenario(0, sheet, config, answers, 0.0, 0.0, (0.0,), tuple(script))


def some(res: Result, kind: EventType) -> list[Event]:
    return [e for e in res.events if e.event is kind]


@pytest.mark.xfail(
    strict=True,
    reason="limits.breach counts every slice_start, so the orphan of an interrupted slice uses up "
    "one slice of RunLimits.max_slices and the resumed run stops a slice earlier than the "
    "uninterrupted one",
)
def test_an_orphaned_slice_start_uses_up_the_slice_limit():
    # One slice of progress, then the finishing one: exactly max_slices = 2 when uninterrupted.
    scn = hand(
        [beh(progress="progress"), beh(progress="all", status="done")],
        limits=RunLimits(max_slices=2),
    )
    ref = run_in_tmp(scn)
    hit = run_in_tmp(scn, interrupts=[(1, False)])  # Ctrl-C as the second slice starts
    assert ref.report.all_passed and hit.world.interrupted == 1
    assert hit.report == ref.report, hit.report  # stopped: 2 slices started; the run limit is 2


@pytest.mark.xfail(
    strict=True,
    reason="firm.run records round_closed after a pause and a resume skips closed rounds, so a "
    "paused run never continues (a one-round run resumes as 'finished' with nothing done)",
)
def test_a_paused_run_can_be_resumed():
    scn = hand([beh(outcome=Outcome.USAGE_LIMIT, cost_kind="unknown"), beh(progress="all")])
    res = run_in_tmp(scn, rerun=True)
    assert some(res, EventType.PAUSED) and res.calls_before_rerun == 1
    assert res.world.invocations == 2 and res.report.all_passed, res.report


TWO_ROUNDS = dict(budgets=(300_000, 400_000), unlocks=(2, 2), answers=("y", "y"))


@pytest.mark.xfail(
    strict=True,
    reason="firm.run enforces a round's unlock threshold only in the invocation that closed it; "
    "a resume skips the closed round and asks the investor to fund the next one",
)
def test_re_running_a_run_closed_below_its_threshold_does_not_fund_the_next_round():
    # 150,000 of round 1's 300,000 is spent on one passing check, then 50,000 more: no cap fits.
    scn = hand([beh(progress="progress", exact=150_000), beh(exact=50_000)], **TWO_ROUNDS)
    res = run_in_tmp(scn, rerun=True)
    assert res.report.stopped is not None and res.calls_before_rerun == 2
    assert some(res, EventType.ROUND_CLOSED)[0].data == {"passed": 1, "total": 2, "unlocked": False}
    assert res.asked == [] and res.world.invocations == 2, res.asked


@pytest.mark.xfail(
    strict=True,
    reason="firm.run asks for the next round after a resume even when every check already passes: "
    "it does not look at the finished run's round_closed event",
)
def test_re_running_a_finished_run_does_not_ask_for_more_money():
    scn = hand([beh(progress="all", status="done")], **TWO_ROUNDS)
    res = run_in_tmp(scn, rerun=True)
    assert res.calls_before_rerun == 1 and res.events_before_rerun == len(res.events) - 2
    assert res.asked == []


@pytest.mark.xfail(
    strict=True,
    reason="budget._unknown_slice_charges charges an unknown-cost slice at its cap while "
    "rundir.slice_end_fields folds the same spend into the next slice's cost, so the round "
    "counts it twice",
)
def test_an_unknown_cost_slice_is_charged_twice():
    # Slice 1's cost is unknown (truly 40,000; charged 100,000). Slice 2 overshoots its 100,000
    # cap by exactly the reserve, as allowed. The CLI's cumulative total is 240,000 in a round of
    # 300,000, yet the round is charged 100,000 + 240,000.
    scn = hand(
        [beh(cost_kind="unknown", exact=40_000, progress="progress"),
         beh(exact=200_000, progress="all", status="done")],
        budgets=(300_000,),
    )  # fmt: skip
    res = run_in_tmp(scn)
    assert sum(c.true_cost for c in res.world.calls) == 240_000
    assert spent_by_round(res.events, scn.sheet)[1] <= 300_000, spent_by_round(
        res.events, scn.sheet
    )


@pytest.mark.xfail(
    strict=True,
    reason="a slice that spent money but died before slice_end leaves only a slice_start, which "
    "budget.remaining ignores, so the resumed slice is capped as if nothing was spent",
)
def test_a_crash_before_slice_end_hides_the_slices_spend_from_the_round():
    # Each slice overshoots its 100,000 cap by less than the 100,000 reserve; 350,000 is spent
    # from a round of 300,000.
    scn = hand(
        [beh(exact=150_000, progress="progress"), beh(exact=200_000, progress="all")],
        budgets=(300_000,),
    )
    res = run_in_tmp(scn, crash_on=[(EventType.SLICE_END, 1)], strict_sessions=False)
    assert res.world.crashed_on == [EventType.SLICE_END]
    assert sum(c.true_cost for c in res.world.calls) <= 300_000


@pytest.mark.xfail(
    strict=True,
    reason="firm._slice sets `resume` from finished slices only; a crash after the CLI created the "
    "session but before slice_end makes the resumed slice start the same session id again",
)
def test_a_crash_before_slice_end_makes_the_next_slice_reuse_the_session_id():
    res = run_in_tmp(
        hand([beh(progress="all", status="done")]), crash_on=[(EventType.SLICE_END, 1)]
    )
    assert res.world.violations == [], res.world.violations


@pytest.mark.xfail(
    strict=True,
    reason="state.slice_history/_latest_gated read a slice_end without check_results as a gated "
    "slice with nothing passing, and nothing gates it again, so the resumed run pays for a "
    "slice the uninterrupted run did not need",
)
def test_a_slice_whose_gate_results_were_lost_is_paid_for_twice():
    scn = hand([beh(progress="all", status="done")])
    ref = run_in_tmp(scn)
    hit = run_in_tmp(scn, crash_on=[(EventType.CHECK_RESULT, 1)])
    assert hit.world.crashed_on == [EventType.CHECK_RESULT]
    assert len(some(ref, EventType.SLICE_START)) == 1
    assert _canon(hit.events) == _canon(ref.events), len(some(hit, EventType.SLICE_START))


STALLS = [beh(progress="progress"), beh(progress="stall"), beh(progress="stall")]


@pytest.mark.xfail(
    strict=True,
    reason="rule.decide runs only right after a live slice (firm._act); a crash between the last "
    "check_result and the fired event loses the decision and the worker is funded again",
)
def test_a_decision_lost_in_a_crash_keeps_funding_a_worker_the_rule_fired():
    scn = hand([*STALLS, beh(progress="all")], policy=FiringPolicy(stall_slices=2, max_slices=6))
    ref = run_in_tmp(scn)
    assert [e.data["reason"] for e in some(ref, EventType.FIRED)] == ["no progress"]
    hit = run_in_tmp(scn, crash_on=[(EventType.FIRED, 1)])
    assert hit.world.crashed_on == [EventType.FIRED]
    assert _canon(hit.events) == _canon(ref.events)


@pytest.mark.xfail(
    strict=True,
    reason="rule.decide runs only right after a live slice (firm._act); a crash between the last "
    "check_result and the blocked/abandoned events loses the escalation and the blocked worker "
    "is funded again",
)
def test_a_decision_lost_in_a_crash_keeps_funding_a_worker_that_said_blocked():
    scn = hand([beh(status="blocked"), beh(progress="all", status="done")])
    ref = run_in_tmp(scn)
    assert [e.data["reason"] for e in some(ref, EventType.ABANDONED)] == ["blocked"]
    hit = run_in_tmp(scn, crash_on=[(EventType.BLOCKED, 1)])
    assert hit.world.crashed_on == [EventType.BLOCKED]
    assert _canon(hit.events) == _canon(ref.events)


@pytest.mark.xfail(
    strict=True,
    reason="firm._current_worker copies the fired worker's files into the replacement's workspace "
    "before recording hired, and handoff.prepare_workspace refuses a non-empty workspace, so a "
    "crash in between makes every resume raise ValueError",
)
def test_a_crash_between_reassigned_and_hired_makes_the_run_unresumable():
    scn = hand(
        [beh(progress="stall"), beh(progress="stall"), beh(progress="all", status="done")],
        policy=FiringPolicy(stall_slices=2, max_slices=6),
    )
    res = run_in_tmp(scn, crash_on=[(EventType.HIRED, 2)])
    assert res.world.crashed_on == [EventType.HIRED]
    assert res.exc is None, res.exc


@pytest.mark.xfail(
    strict=True,
    reason="firm.run closes a round only in the invocation that stopped it; a resume sees the "
    "stopped event, breaks out without recording round_closed and reports 'stopped earlier'",
)
def test_a_crash_between_stopped_and_round_closed_changes_the_report():
    scn = hand([beh(progress="progress")], limits=RunLimits(max_slices=1))
    ref = run_in_tmp(scn)
    assert ref.report.stopped == "stopped: 1 slices started; the run limit is 1"
    hit = run_in_tmp(scn, crash_on=[(EventType.ROUND_CLOSED, 1)])
    assert hit.world.crashed_on == [EventType.ROUND_CLOSED]
    assert hit.report == ref.report and _canon(hit.events) == _canon(ref.events), hit.report
