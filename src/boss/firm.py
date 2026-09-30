"""The firm's round loop. Stage 0: one approved round, one worker, one slice, then the gate.

Every step is written to the ledger before the next one starts, and nothing is spawned until
`require_approval` finds an investor approval matching the current term sheet and checks.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.approval import require_approval
from boss.boss import load_prompt
from boss.errors import Outcome
from boss.gate import CheckResult, run_gate
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.runner import SliceRun, run_slice
from boss.termsheet import TermSheet
from boss.worker import IsolationError, SliceSpec, billing_mode

BUILDER_PROMPT = "builder_v1.md"
DEFAULT_WORKER_MODEL = "haiku"
# kn: the CLI can overshoot a slice cap by one response (+32% in a probe), so a slice gets 80%
# of the round. Multi-round headroom accounting replaces this in stage 2.
SLICE_SHARE = 0.8

SliceRunner = Callable[..., SliceRun]
Gate = Callable[..., list[CheckResult]]


@dataclass(frozen=True, slots=True)
class RunPaths:
    root: Path

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.jsonl"

    @property
    def checks(self) -> Path:
        return self.root / "checks"

    def workspace(self, worker: str) -> Path:
        return self.root / "workspaces" / worker

    def log(self, worker: str) -> Path:
        return self.root / "logs" / f"{worker}.jsonl"


@dataclass(frozen=True, slots=True)
class RoundReport:
    worker: str
    outcome: Outcome
    status: dict[str, Any] | None
    checks: list[CheckResult]
    passed: int
    unlocked: bool
    spend_micros: int | None


@dataclass(frozen=True, slots=True)
class Recorder:
    """Writes ledger events for one run and round."""

    ledger: LedgerWriter
    run_id: str
    round: int

    def __call__(self, actor: str, event: EventType, **fields: Any) -> None:
        self.ledger.append(
            Event(run=self.run_id, round=self.round, actor=actor, event=event, **fields)
        )


def run_first_round(
    sheet: TermSheet,
    paths: RunPaths,
    ledger: LedgerWriter,
    run_id: str,
    *,
    env: Mapping[str, str],
    model: str = DEFAULT_WORKER_MODEL,
    slice_runner: SliceRunner = run_slice,
    gate: Gate = run_gate,
) -> RoundReport:
    require_approval(read_events(paths.ledger), sheet, paths.checks)
    round_, task, worker = sheet.rounds[0], sheet.tasks[0], "w1"
    actor = f"worker:{worker}"
    record = Recorder(ledger, run_id, round_.n)

    spec = SliceSpec(
        session_id=uuid.uuid4(),
        resume=False,
        prompt=task_prompt(sheet, paths),
        model=model,
        cap_micros=max(1, int(round_.budget_micros * SLICE_SHARE)),
        append_system_prompt=load_prompt(BUILDER_PROMPT),
    )
    workspace = paths.workspace(worker)
    workspace.mkdir(parents=True, exist_ok=True)
    record(
        "boss",
        EventType.HIRED,
        data={"worker": worker, "task": task.id, "session": str(spec.session_id), "model": model},
    )
    record(actor, EventType.SLICE_START, data={"slice": 1, "cap_micros": spec.cap_micros})
    try:
        run = slice_runner(spec, workspace, paths.log(worker), env=env)
    except IsolationError as exc:
        record(actor, EventType.ERROR, cost_micros=None, data={"isolation": str(exc)})
        record("boss", EventType.STOPPED, data={"reason": "worker did not start isolated"})
        raise
    _record_slice_end(record, actor, run, env)

    results = gate(workspace, paths.checks, sheet.gate_checks())
    for r in results:
        record(
            "gate",
            EventType.CHECK_RESULT,
            data={
                "check": r.check_id,
                "task": task.id,
                "status": str(r.status),
                "detail": r.detail,
            },
        )
    passed = sum(r.passed for r in results)
    unlocked = passed >= round_.unlock_checks
    record(
        "boss",
        EventType.ROUND_CLOSED,
        data={"passed": passed, "total": len(results), "unlocked": unlocked},
    )
    return RoundReport(
        worker, run.outcome, run.status, results, passed, unlocked, run.usage.cost_micros
    )


def _record_slice_end(record: Recorder, actor: str, run: SliceRun, env: Mapping[str, str]) -> None:
    record(
        actor,
        EventType.SLICE_END,
        cost_micros=run.usage.cost_micros,
        tokens_in=run.usage.tokens_in,
        tokens_out=run.usage.tokens_out,
        tokens_cached=run.usage.tokens_cached,
        billing=billing_mode(env),
        data={
            "slice": 1,
            "outcome": str(run.outcome),
            "status": run.status,
            "exit_code": run.exit_code,
            "denials": len(run.denials),
            "log": str(run.log_path),
        },
    )
    if run.status and run.status.get("status") == "blocked":
        record(actor, EventType.BLOCKED, data={"reason": run.status.get("reason")})


def task_prompt(sheet: TermSheet, paths: RunPaths) -> str:
    """The worker's instructions: its brief, the files it owns, and every check it will face."""
    task = sheet.tasks[0]
    parts = [
        f"Task {task.id}: {task.brief}",
        f"Files you own: {', '.join(task.paths)}",
        "After you stop, an independent gate runs these checks against your files. "
        "You cannot run them yourself.",
    ]
    for check in sheet.checks:
        code = (paths.checks / check.file).read_text(encoding="utf-8").rstrip()
        parts.append(f"--- {check.file}: {check.description}\n{code}")
    parts.append("When you stop, report your status.")
    return "\n\n".join(parts)
