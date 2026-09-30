"""A run's folder layout, its ledger recorder, and the final product assembly."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.handoff import PREVIOUS_DIR
from boss.ledger import Event, EventType, LedgerWriter
from boss.runner import SliceRun
from boss.state import RunState
from boss.termsheet import TermSheet


@dataclass(frozen=True, slots=True)
class RunPaths:
    root: Path

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.jsonl"

    @property
    def checks(self) -> Path:
        return self.root / "checks"

    @property
    def product(self) -> Path:
        return self.root / "product"

    def workspace(self, worker: str) -> Path:
        return self.root / "workspaces" / worker

    def log(self, worker: str) -> Path:
        return self.root / "logs" / f"{worker}.jsonl"


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


def assemble_product(paths: RunPaths, sheet: TermSheet, state: RunState) -> None:
    """Copy each task's files from its current worker's workspace into product/.

    Tasks own disjoint paths (validated on the term sheet), so the copies cannot collide.
    """
    if paths.product.exists():
        shutil.rmtree(paths.product)
    paths.product.mkdir(parents=True)
    for task in sheet.tasks:
        worker = state.tasks[task.id].current
        if worker is None:
            continue
        source = paths.workspace(worker)
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if path.is_file() and not path.is_symlink() and PREVIOUS_DIR not in relative.parts:
                target = paths.product / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)


def slice_end_fields(run: SliceRun, number: int, task: str, previous_total: int) -> dict[str, Any]:
    """Ledger fields for a finished slice. The CLI reports the session's cumulative cost, so the
    slice's own spend is the difference from the total after the previous slice."""
    total = run.usage.cost_micros
    return {
        "cost_micros": None if total is None else max(0, total - previous_total),
        "tokens_in": run.usage.tokens_in,
        "tokens_out": run.usage.tokens_out,
        "tokens_cached": run.usage.tokens_cached,
        "data": {
            "slice": number,
            "task": task,
            "outcome": str(run.outcome),
            "status": run.status,
            "session_total_micros": total,
            "exit_code": run.exit_code,
            "denials": len(run.denials),
            "log": str(run.log_path),
        },
    }
