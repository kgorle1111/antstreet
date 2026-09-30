"""Funding rounds in story-priority order. Planning, not a role: no model call."""

from __future__ import annotations

from collections.abc import Sequence

from boss.budget import min_round_budget, plan_rounds
from boss.roles.stories import PRIORITIES, Stories
from boss.termsheet import CheckSpec, Round


def plan_rounds_by_priority(
    stories: Stories, checks: Sequence[CheckSpec], budget_micros: int, n_rounds: int
) -> tuple[Round, ...]:
    """Split a budget into rounds that unlock in priority order: `must`, then `should`, `could`.

    A check has the priority of the most important criterion it cites; a check that cites no
    known criterion counts as `could`. Round 1 unlocks when as many checks pass as there are
    `must` checks (M), round 2 when M plus the `should` checks pass, and the last round when all
    checks pass. A priority with no checks adds no round. With fewer priorities than `n_rounds`
    there are fewer rounds; with more, the last rounds merge (round 1 is always `must`). A round's
    budget is the smallest budget that can fund a slice (`budget.min_round_budget`) plus a share
    of the rest proportional to the checks it unlocks; rounds are merged from the end until every
    round has that minimum. When all checks share one priority there is nothing to split on and
    this is `budget.plan_rounds`.

    What the count guarantees: an unlock threshold is a NUMBER of passing checks, not a named set.
    Round 1 cannot close until M checks pass, and the run cannot finish until all pass. It does
    not guarantee that those M are the `must` checks: any passing checks count. If N checks
    exist, at least M - (N - M) `must` checks pass when round 1 closes, and that is 0 or less
    whenever `must` checks are half or fewer of all checks. So priority is an ordering of effort
    that the builders follow when they read the checks, not a lock. A check that later regresses
    lowers the count again. Raises ValueError for a non-positive budget, round count or no checks.
    """
    if budget_micros <= 0 or n_rounds <= 0 or not checks:
        raise ValueError("budget_micros, n_rounds and the number of checks must be positive")
    n_rounds = min(n_rounds, budget_micros)  # a round needs at least one micro-dollar
    tiers = _cumulative_tiers(stories, checks)
    if len(tiers) < 2:
        return plan_rounds(budget_micros, len(checks), n_rounds)
    floor = min_round_budget()
    n = min(n_rounds, len(tiers))
    while n > 1 and budget_micros < n * floor:
        n -= 1
    if n == 1:
        return plan_rounds(budget_micros, len(checks), 1)
    unlocks = tiers[: n - 1] + [len(checks)]
    weights = [unlocks[0]] + [b - a for a, b in zip(unlocks, unlocks[1:], strict=False)]
    spare = budget_micros - n * floor
    shares = [spare * w // sum(weights) for w in weights]
    for k in range(spare - sum(shares)):  # under n micro-dollars left: earliest rounds take them
        shares[k] += 1
    return tuple(
        Round(k, floor + share, unlock)
        for k, (share, unlock) in enumerate(zip(shares, unlocks, strict=True), start=1)
    )


def _cumulative_tiers(stories: Stories, checks: Sequence[CheckSpec]) -> list[int]:
    """For each priority that has checks, most important first: how many checks that priority and
    every more important one hold. Strictly increasing, and it ends at len(checks)."""
    lowest = len(PRIORITIES) - 1
    rank = {p: i for i, p in enumerate(PRIORITIES)}
    of_criterion = {
        c.id: rank.get(story.priority, lowest) for story in stories.stories for c in story.criteria
    }
    counts = [0] * len(PRIORITIES)
    for check in checks:
        known = [of_criterion[c] for c in check.criteria if c in of_criterion]
        counts[min(known, default=lowest)] += 1
    tiers, running = [], 0
    for count in counts:
        if count:
            running += count
            tiers.append(running)
    return tiers
