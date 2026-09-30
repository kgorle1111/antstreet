"""Hard limits that stop a whole run: a second layer, independent of the round budget and the
firing rule, so a bug in either cannot spend without bound. Pure functions over the ledger."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from boss.ledger import Event, EventType
from boss.worker import usd


@dataclass(frozen=True, slots=True)
class RunLimits:
    max_slices: int = 60  # slices started in the whole run, infrastructure retries included
    max_workers: int = 16  # workers hired in the whole run
    max_seconds: float | None = None  # wall clock of this invocation; None = no limit

    def __post_init__(self) -> None:
        for name in ("max_slices", "max_workers"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be an int >= 1, got {value!r}")
        s = self.max_seconds
        if s is not None and (isinstance(s, bool) or not isinstance(s, int | float) or not s > 0):
            raise ValueError(f"max_seconds must be None or a number > 0, got {s!r}")


def spend_ceiling(round_budgets_micros: Sequence[int], reserve_micros: int) -> int:
    """The most a run may have spent on its rounds: every round's budget plus one reserve per round
    (the documented worst case is one response of overshoot per round)."""
    if not round_budgets_micros:
        raise ValueError("round_budgets_micros must not be empty")
    if reserve_micros < 0:
        raise ValueError(f"reserve_micros must be non-negative, got {reserve_micros!r}")
    return sum(round_budgets_micros) + reserve_micros * len(round_budgets_micros)


def breach(
    events: Sequence[Event], limits: RunLimits, *, ceiling_micros: int, elapsed_s: float
) -> str | None:
    """None while the run is inside every limit; otherwise one sentence naming the limit, the
    figure reached and the figure allowed.

    Called before each new slice; the first hit wins, in this order:
    spend    breached when known spend in rounds >= 1 is > ceiling_micros (round 0 is the boss's
             drafting call and has its own cap; unknown costs add nothing);
    slices   breached when slice_start events are >= max_slices (the next slice would exceed it);
    workers  breached when hired events are > max_workers (the hiring has already happened);
    clock    breached when elapsed_s is >= max_seconds, if set.
    """
    spent = sum(e.cost_micros or 0 for e in events if e.round >= 1)
    if spent > ceiling_micros:
        return f"spend ${usd(spent)} is over the run ceiling of ${usd(ceiling_micros)}"
    slices = sum(e.event is EventType.SLICE_START for e in events)
    if slices >= limits.max_slices:
        return f"{slices} slices started; the run limit is {limits.max_slices}"
    workers = sum(e.event is EventType.HIRED for e in events)
    if workers > limits.max_workers:
        return f"{workers} workers hired; the run limit is {limits.max_workers}"
    if limits.max_seconds is not None and elapsed_s >= limits.max_seconds:
        return f"{elapsed_s:.0f}s of wall clock elapsed; the run limit is {limits.max_seconds:g}s"
    return None
