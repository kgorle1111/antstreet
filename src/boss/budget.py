"""Round budgets, slice caps and the round plan. Pure integer arithmetic; money is micro-dollars."""

from __future__ import annotations

from collections.abc import Sequence

from boss.errors import INFRASTRUCTURE
from boss.ledger import Event, EventType, Totals, total
from boss.termsheet import Round, TermSheet

# The CLI checks a slice's cap only between model responses, so a slice can overshoot by one whole
# response whatever the cap is: measured on Haiku, a $0.030 cap spent $0.099. The reserve is that
# one response, held back from every cap. A percentage of the cap cannot cover it.
# A larger model's response costs more, so the figure is per model family. Only Haiku was measured;
# the others scale it by the ratio of output-token list prices (3x for Sonnet, 5x for Opus), so
# re-measure them as D18 did before relying on the tighter side of them.
RESERVE_MICROS = 100_000  # Haiku, and the figure for a model whose family is not recognised
_FAMILY_RESERVES = (
    ("haiku", RESERVE_MICROS),
    ("sonnet", 3 * RESERVE_MICROS),
    ("opus", 5 * RESERVE_MICROS),
)
MODEL_RESERVE = -1  # in a FirmConfig: "the reserve for this config's model"
MIN_SLICE_MICROS = 5_000
_INFRASTRUCTURE = frozenset(str(outcome) for outcome in INFRASTRUCTURE)


def reserve_for(model: str) -> int:
    """The reserve for a worker model, from an alias (`sonnet`) or a full id."""
    name = model.lower()
    return next((micros for family, micros in _FAMILY_RESERVES if family in name), RESERVE_MICROS)


def _round(sheet: TermSheet, round_n: int) -> Round:
    for r in sheet.rounds:
        if r.n == round_n:
            return r
    raise ValueError(f"round {round_n} is not in the term sheet")


def is_top_up(event: Event) -> bool:
    """Only the investor adds money: a worker's or a role's `topped_up` event counts for nothing."""
    return event.event is EventType.TOPPED_UP and event.actor == "investor"


def round_budget(sheet: TermSheet, events: Sequence[Event], round_n: int) -> int:
    """Term-sheet budget plus every investor top-up recorded in this round."""
    budget = _round(sheet, round_n).budget_micros
    for e in events:
        if e.round == round_n and is_top_up(e):
            micros = e.data.get("micros")
            if type(micros) is not int or micros <= 0:
                raise ValueError(f"topped_up micros must be a positive int, got {micros!r}")
            budget += micros
    return budget


def round_spend(events: Sequence[Event], round_n: int) -> Totals:
    """Ledger totals for one round across all actors."""
    return total(e for e in events if e.round == round_n)


def remaining(sheet: TermSheet, events: Sequence[Event], round_n: int) -> int:
    """What the round can still spend. Negative after an overshoot.

    A slice that did work but reported no cost (a crash, a kill at the timeout) is charged at its
    cap, and so is a slice that started and never reported an end (the run was interrupted):
    treating either as free would let a round fund such slices without end. An infrastructure
    failure (login, rate limit) reported no cost because it did no work, so it is not charged.
    The charge is dropped once a later slice resumes the same session and reports its total: that
    total covers the lost slice's real spend, which the later slice's cost then books.

    Call this between slices only: a slice still running looks like one that never ended.
    """
    spent = round_spend(events, round_n).cost_micros + _unknown_slice_charges(events, round_n)
    return round_budget(sheet, events, round_n) - spent


def _unknown_slice_charges(events: Sequence[Event], round_n: int) -> int:
    # Slices started and not yet ended, and slices lost, each as cap and session, by round.
    unfinished: dict[tuple[int, str, object], tuple[int, object]] = {}
    lost: list[tuple[int, int, object]] = []  # (round, cap, session)
    for e in events:
        key = (e.round, e.actor, e.data.get("slice"))
        if e.event is EventType.SLICE_START:
            if key in unfinished:  # the same slice started again: the first was lost
                lost.append((e.round, *unfinished[key]))
            cap = e.data.get("cap_micros")
            unfinished[key] = (cap if type(cap) is int and cap > 0 else 0, e.data.get("session"))
        elif e.event is EventType.SLICE_END:
            cap, session = unfinished.pop(key, (0, None))
            if session is not None and type(e.data.get("session_total_micros")) is int:
                # A resumed session reports its cumulative cost: this slice's cost already holds
                # what every earlier slice of the session spent, whichever round booked it.
                lost = [x for x in lost if x[2] != session]
                unfinished = {k: v for k, v in unfinished.items() if v[1] != session}
            if e.cost_micros is None and e.data.get("outcome") not in _INFRASTRUCTURE:
                lost.append((e.round, cap, session))
    return sum(cap for r, cap, _ in lost if r == round_n) + sum(
        cap for k, (cap, _) in unfinished.items() if k[0] == round_n
    )


def next_slice_cap(
    remaining_micros: int,
    *,
    slice_micros: int,
    reserve_micros: int = RESERVE_MICROS,
    min_cap: int = MIN_SLICE_MICROS,
) -> int | None:
    """Largest cap <= slice_micros that leaves `reserve_micros` of the round unspent.

    A slice that overshoots its cap by at most the reserve therefore never takes the round past
    its budget. None when that cap is below `min_cap`: the round cannot fund another slice.
    """
    if reserve_micros < 0:
        raise ValueError(f"reserve_micros must be non-negative, got {reserve_micros!r}")
    cap = min(slice_micros, remaining_micros - reserve_micros)
    return cap if cap >= min_cap else None


def min_round_budget(reserve_micros: int = RESERVE_MICROS, min_cap: int = MIN_SLICE_MICROS) -> int:
    """The smallest round budget that can fund one slice."""
    return reserve_micros + min_cap


def unlocked(
    sheet: TermSheet, round_n: int, passing_checks: int, total_checks: int | None = None
) -> bool:
    """`total_checks` is what is still required after the investor dropped any: a threshold
    written for the full sheet cannot ask for more checks than remain."""
    threshold = _round(sheet, round_n).unlock_checks
    if total_checks is not None:
        threshold = min(threshold, total_checks)
    return passing_checks >= threshold


def plan_rounds(budget_micros: int, n_checks: int, n_rounds: int = 3) -> tuple[Round, ...]:
    """Split a budget into equal-as-possible rounds, earliest rounds taking the remainder."""
    if budget_micros <= 0 or n_checks <= 0 or n_rounds <= 0:
        raise ValueError("budget_micros, n_checks and n_rounds must be positive")
    rounds = min(n_rounds, n_checks)
    if budget_micros < rounds:
        raise ValueError(f"budget of {budget_micros} micros cannot fund {rounds} rounds")
    base, extra = divmod(budget_micros, rounds)
    return tuple(
        Round(
            n=k,
            budget_micros=base + (1 if k <= extra else 0),
            unlock_checks=-(-n_checks * k // rounds),
        )
        for k in range(1, rounds + 1)
    )
