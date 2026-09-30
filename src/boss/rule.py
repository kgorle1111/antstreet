"""The firing rule: decide, from a worker's slice history alone, whether to fund its next slice.

Pure and deterministic, so the same function runs live and in offline replay. It never sees model
output: only what each slice cost, how it ended, and which of the task's checks passed after it.
Infrastructure failures and blocked workers are never counted against a worker, and a worker
whose only failing checks are ones it disputes is sent to the investor, not fired: in the pilot
the boss wrote wrong checks, and correct workers stalled on them until the rule fired them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from boss.errors import INFRASTRUCTURE, Outcome


class Decision(StrEnum):
    CONTINUE = "continue"  # fund another slice
    DONE = "done"  # every check of the task passes
    FIRE = "fire"  # stop funding this worker
    ESCALATE = "escalate"  # the investor must decide (blocked, refusal, disputed checks)
    RETRY = "retry"  # infrastructure problem: run the slice again later, uncounted


@dataclass(frozen=True, slots=True)
class SliceRecord:
    """What is known after one slice of one worker on one task."""

    slice: int  # 1-based
    cost_micros: int | None  # this slice's own spend; None when unknown
    outcome: Outcome
    status: str  # the worker's self-report: "done", "continuing", "blocked" or "none"
    passing: frozenset[str]  # ids of the task's checks that pass after this slice
    disputed: frozenset[str] = frozenset()  # checks the worker disputed in this slice


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
    """The decision after the latest slice in `history` (which must be non-empty).

    Rules apply in order to the latest record; the first that matches wins, so DONE beats an
    infrastructure retry and both beat the slice limit. Infrastructure slices are never counted,
    but the checks they show passing still count as "seen" when judging later progress.
    """
    if not history or not task_checks:
        raise ValueError("decide needs a non-empty history and a non-empty task_checks")

    latest = history[-1]
    seen: set[str] = set()
    raised: set[str] = set()
    counted = stalled = spent = unknown = 0
    for record in history:
        raised |= record.disputed
        if record.outcome not in INFRASTRUCTURE:
            counted += 1
            stalled = 0 if record.passing - seen else stalled + 1
        seen |= record.passing
        if record.cost_micros is None:
            unknown += 1
        else:
            spent += record.cost_micros

    # A dispute stands only while its check fails, and never makes a check count as passing.
    disputed = (raised & task_checks) - latest.passing
    evidence: dict[str, Any] = {
        "counted_slices": counted,
        "stalled_slices": stalled,
        "passing": sorted(latest.passing),
        "best": sorted(seen),
        "missing": sorted(task_checks - latest.passing),
        "disputed": sorted(disputed),
        "spent_micros": spent,
        "unknown_cost_slices": unknown,
    }

    def verdict(decision: Decision, reason: str) -> Verdict:
        return Verdict(decision, reason, evidence)

    if task_checks <= latest.passing:
        return verdict(Decision.DONE, "all checks pass")
    if latest.outcome in INFRASTRUCTURE:
        return verdict(Decision.RETRY, f"infrastructure: {latest.outcome.value}")
    if latest.status == "blocked":
        return verdict(Decision.ESCALATE, "blocked")
    if latest.outcome is Outcome.REFUSAL:
        return verdict(Decision.ESCALATE, "refusal")
    if disputed and task_checks - latest.passing <= disputed:
        return verdict(Decision.ESCALATE, "disputed")
    if counted >= policy.max_slices:
        return verdict(Decision.FIRE, "slice limit")
    if stalled >= policy.stall_slices:
        return verdict(Decision.FIRE, "no progress")
    return verdict(Decision.CONTINUE, "progressing")
