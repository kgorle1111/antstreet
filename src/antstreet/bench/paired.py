"""A paired comparison of two arms by task: mean per-task difference with a task-level bootstrap.

The task, not the run, is the unit: runs of one task are summarised first, so a task that was run
more often does not count more. Infrastructure failures are excluded (and counted), like in the
table. Pure functions over loaded results; no model calls.
"""

from __future__ import annotations

import argparse
import math
import random
import statistics
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from antstreet.bench.results import ARMS, CellResult, load_results
from antstreet.bench.table import _counted, _visible_pass

# One task makes every resample the same, so its interval is a point and proves nothing. The
# percentile bootstrap is also optimistic for a handful of tasks; this only stops the empty case.
MIN_TASKS = 2
LEVEL = 0.95

# Per-task value of each KPI, from that task's counted runs of one arm.
_KPIS: dict[str, Callable[[Sequence[CellResult]], float]] = {
    "delivery": lambda rs: sum(r.passed for r in rs) / len(rs),
    # pass^k: 1 when every counted run delivered. Comparable only at one k, which compare enforces.
    "pass_all": lambda rs: float(all(r.passed for r in rs)),
    "false_pass": lambda rs: sum(_visible_pass(r) and not r.passed for r in rs) / len(rs),
    # The mean cost of all the task's runs, delivered or not: a task's cost per delivery is
    # undefined when it delivered nothing, and dropping those tasks would favour the arm that fails.
    "cost_per_delivery": lambda rs: sum(r.cost_micros for r in rs) / len(rs) / 1e6,
    "time": lambda rs: statistics.median(r.duration_s for r in rs),
}
KPIS = tuple(_KPIS)
HIGHER_IS_BETTER = {"delivery", "pass_all"}


@dataclass(frozen=True, slots=True)
class Paired:
    arm_a: str
    arm_b: str
    kpi: str
    set_hash: str
    tasks: int
    mean: float  # A - B
    low: float
    high: float
    resamples: int
    seed: int
    infrastructure: int  # cells excluded from either side
    unpaired: int  # tasks with no counted run on both sides
    unknown_cost_cells: int = (
        0  # counted cells with an event of unknown cost: cost is a lower bound
    )

    @property
    def shown(self) -> bool:
        """The interval excludes 0 in A's favour: above it for delivery and pass_all, below it
        otherwise."""
        if self.tasks < MIN_TASKS:
            return False
        return self.low > 0 if self.kpi in HIGHER_IS_BETTER else self.high < 0


def task_values(cells: Sequence[CellResult], arm: str, kpi: str) -> dict[str, float]:
    """Task id -> the KPI over that task's counted runs of `arm`; tasks with none are absent."""
    mine = _counted([c for c in cells if c.arm == arm])
    return {
        task: _KPIS[kpi]([c for c in mine if c.task == task])
        for task in sorted({c.task for c in mine})
    }


def bootstrap_interval(
    diffs: Sequence[float], resamples: int, seed: int, level: float = LEVEL
) -> tuple[float, float]:
    """Percentile interval of the mean over task resamples drawn with replacement."""
    if not diffs:
        raise ValueError("no differences to resample")
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(statistics.fmean(rng.choices(diffs, k=n)) for _ in range(resamples))
    tail = (1 - level) / 2
    return means[math.floor(tail * resamples)], means[math.ceil((1 - tail) * resamples) - 1]


def compare(
    cells_a: Sequence[CellResult],
    cells_b: Sequence[CellResult],
    arm_a: str,
    arm_b: str,
    kpi: str,
    *,
    resamples: int = 10_000,
    seed: int = 0,
) -> Paired:
    if kpi not in _KPIS:
        raise ValueError(f"kpi must be one of {KPIS}, got {kpi!r}")
    if resamples < 1:
        raise ValueError(f"resamples must be at least 1, got {resamples}")
    if kpi == "false_pass" and not {arm_a, arm_b} <= {"firm"}:
        raise ValueError("false_pass needs visible checks, which only the firm arm has")
    mine_a = [c for c in cells_a if c.arm == arm_a]
    mine_b = [c for c in cells_b if c.arm == arm_b]
    for arm, mine in ((arm_a, mine_a), (arm_b, mine_b)):
        if not mine:
            raise ValueError(f"no results for arm {arm!r}")
    hashes = {c.set_hash for c in (*mine_a, *mine_b)}
    if len(hashes) != 1:
        raise ValueError(f"the two sides ran different task sets: {sorted(hashes)}")
    values_a, values_b = task_values(mine_a, arm_a, kpi), task_values(mine_b, arm_b, kpi)
    both = sorted(values_a.keys() & values_b.keys())
    if not both:
        raise ValueError("no task has a counted run on both sides")
    if kpi == "pass_all":
        _same_runs(_counted(mine_a), _counted(mine_b), both)
    diffs = [values_a[t] - values_b[t] for t in both]
    low, high = bootstrap_interval(diffs, resamples, seed)
    all_tasks = {c.task for c in (*mine_a, *mine_b)}
    return Paired(
        arm_a=arm_a,
        arm_b=arm_b,
        kpi=kpi,
        set_hash=hashes.pop(),
        tasks=len(both),
        mean=statistics.fmean(diffs),
        low=low,
        high=high,
        resamples=resamples,
        seed=seed,
        infrastructure=len(mine_a) + len(mine_b) - len(_counted(mine_a)) - len(_counted(mine_b)),
        unpaired=len(all_tasks) - len(both),
        unknown_cost_cells=sum(
            c.unknown_cost_events > 0 for c in (*_counted(mine_a), *_counted(mine_b))
        ),
    )


def _same_runs(
    counted_a: Sequence[CellResult], counted_b: Sequence[CellResult], tasks: Sequence[str]
) -> None:
    """pass^k with a smaller k is easier to meet, so every compared task needs the same number of
    counted runs on both sides."""
    ks = {sum(c.task == t for c in side) for side in (counted_a, counted_b) for t in tasks}
    if len(ks) > 1:
        raise ValueError(
            f"pass_all needs the same number of counted runs of every task on both sides, got "
            f"{sorted(ks)}; rerun the infrastructure cells"
        )


def _mixed(cells_a: Sequence[CellResult], cells_b: Sequence[CellResult]) -> list[str]:
    return [
        f"{field} differs between the sides"
        for field in ("model", "budget_micros")
        if len({getattr(c, field) for c in (*cells_a, *cells_b)}) > 1
    ]


def render(p: Paired) -> str:
    unit = {
        "delivery": "share",
        "pass_all": "share",
        "false_pass": "share",
        "cost_per_delivery": "$",
        "time": "s",
    }
    places = 4 if p.kpi != "time" else 1

    def num(x: float) -> str:
        return f"{x:+.{places}f}"

    return "\n".join(
        [
            f"paired {p.arm_a} vs {p.arm_b}, {p.kpi} ({unit[p.kpi]}), task set {p.set_hash}",
            f"tasks: {p.tasks} (not on both sides: {p.unpaired}; infrastructure cells excluded: "
            f"{p.infrastructure})",
            f"mean difference ({p.arm_a} - {p.arm_b}): {num(p.mean)}",
            f"95% interval: [{num(p.low)}, {num(p.high)}] "
            f"({p.resamples} task resamples, seed {p.seed})",
            f"verdict: {'shown' if p.shown else 'not shown'}",
        ]
        + (
            [
                f"WARNING: {p.unknown_cost_cells} counted cell(s) have events of unknown cost "
                "(counted as 0 here): each side's cost is a lower bound."
            ]
            if p.kpi == "cost_per_delivery" and p.unknown_cost_cells
            else []
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m antstreet.bench.paired", description=__doc__)
    parser.add_argument("dir_a", type=Path)
    parser.add_argument("dir_b", type=Path)
    parser.add_argument("--arm-a", choices=ARMS, default="firm")
    parser.add_argument("--arm-b", choices=ARMS, default="single")
    parser.add_argument("--kpi", choices=KPIS, default="delivery")
    parser.add_argument("--resamples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        cells_a, cells_b = load_results(args.dir_a), load_results(args.dir_b)
        paired = compare(
            cells_a,
            cells_b,
            args.arm_a,
            args.arm_b,
            args.kpi,
            resamples=args.resamples,
            seed=args.seed,
        )
    except (OSError, ValueError) as exc:
        print(f"cannot compare: {exc}", file=sys.stderr)
        return 1
    mine_a = [c for c in cells_a if c.arm == args.arm_a]
    mine_b = [c for c in cells_b if c.arm == args.arm_b]
    for warning in _mixed(mine_a, mine_b):
        print(f"WARNING: {warning}; the comparison is confounded.")
    print(render(paired))
    return 0


if __name__ == "__main__":
    sys.exit(main())
