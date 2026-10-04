"""A run's folder layout, its ledger recorder, and the final product assembly."""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from boss.handoff import SKIPPED_NAMES
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.redact import safe_text
from boss.runner import SliceRun
from boss.signing import KEY_FILE
from boss.state import RunState
from boss.termsheet import TermSheet
from boss.worker import clean_status


@dataclass(frozen=True, slots=True)
class RunPaths:
    root: Path

    @property
    def investor_key(self) -> Path | None:
        """The project's investor key when this folder is `<project>/.boss/runs/<id>`, else None
        (a folder laid out any other way, such as a test's, has no project to hold one)."""
        runs = self.root.parent
        if runs.name != "runs" or runs.parent.name != ".boss":
            return None
        return runs.parent / KEY_FILE

    @property
    def ledger(self) -> Path:
        return self.root / "ledger.jsonl"

    def events(self) -> list[Event]:
        """The ledger, vouched for by the project's investor key (`ledger.read_events`)."""
        return read_events(self.ledger, self.investor_key)

    def writer(self) -> LedgerWriter:
        """The ledger's writer: it signs the investor's events with the project's key."""
        return LedgerWriter(self.ledger, self.investor_key)

    @property
    def checks(self) -> Path:
        return self.root / "checks"

    @property
    def held_out(self) -> Path:
        return self.root / "held_out"

    @property
    def examiner_refused(self) -> Path:
        return self.root / "examiner_refused.json"

    @property
    def product(self) -> Path:
        return self.root / "product"

    def workspace(self, worker: str) -> Path:
        return self.root / "workspaces" / worker

    def log(self, worker: str) -> Path:
        return self.root / "logs" / f"{worker}.jsonl"

    def prompt(self, worker: str, number: int) -> Path:
        """The exact text a worker's slice was given (`context.write_prompt`)."""
        return self.root / "logs" / f"{worker}-s{number}.prompt.txt"


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


class WorkspaceTooBig(Exception):
    """A worker's folder is over the size limit; the gate would copy it once per check."""

    def __init__(self, worker: str, size: int, limit: int) -> None:
        super().__init__(
            f"the folder of {worker} holds more than {limit // 2**20} MB "
            f"({size // 2**20} MB counted before stopping); the gate copies it for every check"
        )


def workspace_bytes(workspace: Path, stop_at: int) -> int:
    """Bytes of the files under `workspace`, counting a symlink as itself and never following
    one. Stops counting once the total passes `stop_at`: the caller only needs to know that."""
    total = 0
    for root, _dirs, files in os.walk(workspace):  # followlinks=False
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue  # removed while counting
            if total > stop_at:
                return total
    return total


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


_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
MAX_DENIAL_REASONS = 5
MAX_DENIAL_REASON_CHARS = 160


def denial_reasons(denials: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """One cleaned, short reason per distinct refused call, for the next brief: the first
    sentence of the CLI's message about it. A call the CLI gave no message for has none."""
    found: list[dict[str, str]] = []
    for denial in denials:
        message = denial.get("message")
        if not isinstance(message, str):
            continue
        # Bounded before the split: the message is the CLI's text about a worker's call.
        sentence = _SENTENCE_END.split(" ".join(message[:2_000].split()), maxsplit=1)[0]
        reason = {
            "tool": safe_text(str(denial.get("tool")), limit=40),
            "reason": safe_text(sentence, limit=MAX_DENIAL_REASON_CHARS),
        }
        if reason["reason"] and reason not in found:
            found.append(reason)
    return found[:MAX_DENIAL_REASONS]


def slice_end_fields(
    run: SliceRun,
    number: int,
    task: str,
    previous_total: int,
    previous_tokens: tuple[int, int, int],
    *,
    with_model_id: bool = False,
) -> dict[str, Any]:
    """Ledger fields for a finished slice. The CLI reports the session's cumulative cost and
    tokens, so the slice's own are the difference from the totals after the previous slice. A
    slice with no totals books the tokens of its own messages and reports no session tokens."""
    total, usage = run.usage.cost_micros, run.usage
    tokens = (usage.tokens_in, usage.tokens_out, usage.tokens_cached)
    if usage.cumulative:
        tokens_in, tokens_out, tokens_cached = (
            max(0, now - before) for now, before in zip(tokens, previous_tokens, strict=True)
        )
    else:
        tokens_in, tokens_out, tokens_cached = tokens
    data = {
        "slice": number,
        "task": task,
        "outcome": str(run.outcome),
        "status": clean_status(run.status),
        "session_total_micros": total,
        "session_total_tokens": list(tokens) if usage.cumulative else None,
        "exit_code": run.exit_code,
        "denials": len(run.denials),
        "denied_tools": sorted({safe_text(str(d.get("tool")), limit=40) for d in run.denials}),
        "denial_reasons": denial_reasons(run.denials),
        "log": str(run.log_path),
    }
    if with_model_id:
        data["model_id"] = run.model_id
    return {
        "cost_micros": None if total is None else max(0, total - previous_total),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_cached": tokens_cached,
        "data": data,
    }
