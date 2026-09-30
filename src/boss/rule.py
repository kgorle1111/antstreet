"""The firing rule: decide, from a worker's slice history alone, whether to fund its next slice.

Pure and deterministic, so the same function runs live and in offline replay. It never sees model
output: only what each slice cost, how it ended, and which of the task's checks passed after it.
Infrastructure failures and blocked workers are never counted against a worker.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from boss.errors import Outcome


class Decision(StrEnum):
    CONTINUE = "continue"  # fund another slice
    DONE = "done"  # every check of the task passes
    FIRE = "fire"  # stop funding this worker
    ESCALATE = "escalate"  # the investor must decide (blocked, refusal)
    RETRY = "retry"  # infrastructure problem: run the slice again later, uncounted


@dataclass(frozen=True, slots=True)
class SliceRecord:
    """What is known after one slice of one worker on one task."""

    slice: int  # 1-based
    cost_micros: int | None  # this slice's own spend; None when unknown
    outcome: Outcome
    status: str  # the worker's self-report: "done", "continuing", "blocked" or "none"
    passing: frozenset[str]  # ids of the task's checks that pass after this slice


@dataclass(frozen=True, slots=True)
class FiringPolicy:
    stall_slices: int = 2  # fire after this many counted slices in a row with no new passing check
    max_slices: int = 6  # fire once a worker has used this many counted slices

    def __post_init__(self) -> None:
        if self.stall_slices < 1 or self.max_slices < 1:
            raise ValueError("stall_slices and max_slices must be at least 1")


@dataclass(frozen=True, slots=True)
class Verdict:
    decision: Decision
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)  # recorded verbatim in the ledger


def decide(
    task_checks: frozenset[str], history: Sequence[SliceRecord], policy: FiringPolicy
) -> Verdict:
    """The decision after the latest slice in `history` (which must be non-empty)."""
    raise NotImplementedError
