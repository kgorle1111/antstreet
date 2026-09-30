"""A run's folder layout, its ledger recorder, and the final product assembly."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from boss.handoff import SKIPPED_NAMES
from boss.ledger import Event, EventType, LedgerWriter
from boss.redact import safe_text
from boss.runner import SliceRun
from boss.state import RunState
from boss.termsheet import TermSheet
from boss.worker import clean_status


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


def assemble_product(paths: RunPaths, sheet: TermSheet, state: RunState) -> list[str]:
    """Copy each task's files from its best worker's workspace into product/. Returns the
    relative paths that could not be placed.

    A file inside a task's paths always comes from that task's worker. A file no task owns (a
    helper a worker added) comes from the first task that has it. So a worker can never replace
    a file another task's checks passed on, whatever it writes in its own workspace.
    """
    if paths.product.exists():
        shutil.rmtree(paths.product)
    paths.product.mkdir(parents=True)
    owned = [(task.id, PurePosixPath(path)) for task in sheet.tasks for path in task.paths]

    def owner(relative: PurePosixPath) -> str | None:
        return next((t for t, p in owned if p == relative or p in relative.parents), None)

    skipped: list[str] = []
    for task in sheet.tasks:
        worker = state.tasks[task.id].best
        if worker is None:
            continue
        source = paths.workspace(worker)
        for path in sorted(source.rglob("*")):
            relative = PurePosixPath(path.relative_to(source).as_posix())
            if not path.is_file() or path.is_symlink() or SKIPPED_NAMES & set(relative.parts):
                continue
            target = paths.product / relative
            belongs_to = owner(relative)
            if belongs_to not in (None, task.id) or (belongs_to is None and target.is_file()):
                continue
            try:  # one task's file `x` and another's `x/y.py` cannot both be placed
                if target.is_dir():  # copy2 would put the file inside the folder
                    raise IsADirectoryError(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            except OSError:
                skipped.append(relative.as_posix())
    return skipped


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
            "status": clean_status(run.status),
            "session_total_micros": total,
            "exit_code": run.exit_code,
            "denials": len(run.denials),
            "denied_tools": sorted({safe_text(str(d.get("tool")), limit=40) for d in run.denials}),
            "log": str(run.log_path),
        },
    }
