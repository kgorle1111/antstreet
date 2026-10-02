"""The benchmark results table, as markdown.

Infrastructure failures say nothing about either arm, so they are excluded from every rate but
listed in their own column. Costs are the CLI's estimates; events of unknown cost are counted
beside them, never folded in as zero. Every rate carries its sample size and a Wilson interval.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from boss.bench.results import ARMS, CellResult, load_results
from boss.report import dollars

CLOSING = (
    "Pass rates from fewer than ~60 paired tasks cannot show a 20-point difference; "
    "treat them as descriptive."
)
MIXED_WARNING = "WARNING: results mix task sets, models or budgets; do not compare."


@dataclass(frozen=True, slots=True)
class ArmSummary:
    arm: str
    cells: int  # results counted (infrastructure failures excluded)
    infrastructure: int
    tasks: int
    passed: int
    pass_rate: float
    pass_low: float
    pass_high: float
    check_rate: float
    mean_cost_micros: float
    cost_per_pass_micros: float | None
    boss_share: float
    unknown_cost_events: int
    visible_pass_cells: int | None  # firm only
    gamed_cells: int | None  # firm only: every visible check passed, a hidden one did not
    wrong_checks: int | None = None  # firm only: boss checks the reference solution fails
    boss_checks: int | None = None  # boss checks in the cells where that was measured
    wrong_check_cells: int | None = None  # cells whose draft held at least one wrong check
    held_out_wrong: int | None = None  # firm only: held-out checks the reference solution fails
    held_out_checks: int | None = None  # held-out checks in the cells where that was measured
    held_out_wrong_cells: int | None = None  # cells with at least one wrong held-out check
    median_duration_s: float | None = None  # wall clock per counted cell; None with no cells
    reliable_tasks: int = 0  # tasks whose every counted run passed (pass^k over k runs)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    low = 0.0 if successes == 0 else max(0.0, centre - margin)
    high = 1.0 if successes == n else min(1.0, centre + margin)
    return (low, high)


def _counted(results: Sequence[CellResult]) -> list[CellResult]:
    return [r for r in results if r.failure_class != "infrastructure"]


def _visible_pass(r: CellResult) -> bool:
    return (
        r.visible_total is not None and r.visible_total > 0 and r.visible_passed == r.visible_total
    )


def _check_rate(r: CellResult) -> float:
    return r.hidden_passed / r.hidden_total if r.hidden_total else 0.0


def _summarize_arm(arm: str, results: Sequence[CellResult]) -> ArmSummary:
    cells = _counted(results)
    n = len(cells)
    passed = sum(r.passed for r in cells)
    cost = sum(r.cost_micros for r in cells)
    low, high = wilson_interval(passed, n)
    firm = arm == "firm"
    measured = [r for r in cells if r.wrong_checks is not None]
    held = [r for r in cells if r.held_out_wrong is not None]
    return ArmSummary(
        arm=arm,
        cells=n,
        infrastructure=len(results) - n,
        tasks=len({r.task for r in cells}),
        passed=passed,
        pass_rate=passed / n if n else 0.0,
        pass_low=low,
        pass_high=high,
        check_rate=sum(_check_rate(r) for r in cells) / n if n else 0.0,
        mean_cost_micros=cost / n if n else 0.0,
        cost_per_pass_micros=cost / passed if passed else None,
        boss_share=sum(r.boss_micros for r in cells) / cost if cost else 0.0,
        unknown_cost_events=sum(r.unknown_cost_events for r in cells),
        visible_pass_cells=sum(_visible_pass(r) for r in cells) if firm else None,
        gamed_cells=sum(_visible_pass(r) and not r.passed for r in cells) if firm else None,
        wrong_checks=sum(r.wrong_checks or 0 for r in measured) if measured else None,
        boss_checks=sum(r.visible_total or 0 for r in measured) if measured else None,
        wrong_check_cells=sum(bool(r.wrong_checks) for r in measured) if measured else None,
        held_out_wrong=sum(r.held_out_wrong or 0 for r in held) if held else None,
        held_out_checks=sum(r.held_out_total or 0 for r in held) if held else None,
        held_out_wrong_cells=sum(bool(r.held_out_wrong) for r in held) if held else None,
        median_duration_s=statistics.median(r.duration_s for r in cells) if cells else None,
        reliable_tasks=sum(
            all(r.passed for r in cells if r.task == task) for task in {r.task for r in cells}
        ),
    )


def summarize(results: Sequence[CellResult]) -> list[ArmSummary]:
    return [
        _summarize_arm(arm, [r for r in results if r.arm == arm])
        for arm in ARMS
        if any(r.arm == arm for r in results)
    ]


def per_task(results: Sequence[CellResult]) -> list[tuple[str, dict[str, tuple[int, int]]]]:
    """Per task and arm: (passed cells, counted cells). A task run only into infrastructure
    failures still appears, as 0 of 0."""
    rows = []
    for task in sorted({r.task for r in results}):
        arms: dict[str, tuple[int, int]] = {}
        for arm in ARMS:
            mine = [r for r in results if r.task == task and r.arm == arm]
            if mine:
                counted = _counted(mine)
                arms[arm] = (sum(r.passed for r in counted), len(counted))
        rows.append((task, arms))
    return rows


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _rate(s: ArmSummary) -> str:
    return f"{_pct(s.pass_rate)} [{s.pass_low * 100:.0f}-{s.pass_high * 100:.0f}%]"


def _md(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    return [line(header), line(["---"] * len(header))] + [line(r) for r in rows]


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _values(label: str, values: Sequence[str]) -> str:
    return f"{label}: " + ", ".join(sorted(set(values)))


def render_table(results: Sequence[CellResult]) -> str:
    if not results:
        raise ValueError("cannot tabulate an empty result set")
    header = " | ".join(
        [
            _values("Task set", [r.set_hash for r in results]),
            _values("Model", [r.model for r in results]),
            _values("Budget per cell", [dollars(r.budget_micros) for r in results]),
        ]
    )
    mixed = any(
        len({getattr(r, f) for r in results}) > 1 for f in ("set_hash", "model", "budget_micros")
    )
    out = [header] + ([MIXED_WARNING] if mixed else []) + [""]

    summaries = summarize(results)
    rows = []
    for s in summaries:
        has_cells = s.cells > 0
        per_pass = (
            "n/a" if s.cost_per_pass_micros is None else dollars(round(s.cost_per_pass_micros))
        )
        rows.append(
            [
                s.arm,
                str(s.cells),
                str(s.tasks),
                str(s.passed),
                _rate(s),
                _pct(s.check_rate),
                dollars(round(s.mean_cost_micros)) if has_cells else "n/a",
                per_pass,
                _pct(s.boss_share),
                str(s.unknown_cost_events),
                str(s.infrastructure),
                _duration(s.median_duration_s),
                f"{s.reliable_tasks}/{s.tasks}",
            ]
        )
    out += _md(
        [
            "arm",
            "cells",
            "tasks",
            "passed",
            "pass rate [95% CI]",
            "hidden checks",
            "mean cost/cell",
            "cost/pass",
            "boss share",
            "unknown-cost events",
            "infrastructure excluded",
            "median time/cell",
            "tasks passed every run",
        ],
        rows,
    )

    firm = next((s for s in summaries if s.arm == "firm"), None)
    if firm is not None:
        out += [
            "",
            f"Visible vs hidden: {firm.visible_pass_cells} of {firm.cells} firm cells passed "
            f"every visible check; {firm.gamed_cells} of those failed a hidden check.",
        ]
        if firm.wrong_checks is not None:
            out.append(
                f"Wrong boss checks: {firm.wrong_checks} of {firm.boss_checks} checks failed on "
                f"the reference solution, in {firm.wrong_check_cells} drafts."
            )
        if firm.held_out_wrong is not None:
            out.append(
                f"Wrong held-out checks: {firm.held_out_wrong} of {firm.held_out_checks} checks "
                f"failed on the reference solution, in {firm.held_out_wrong_cells} cells."
            )

    tasks = per_task(results)
    arms = [s.arm for s in summaries]
    cells = [
        [task] + [f"{a[0]}/{a[1]}" if (a := by_arm.get(arm)) else "-" for arm in arms]
        for task, by_arm in tasks
    ]
    out += ["", *_md(["task", *arms], cells), "", CLOSING]
    return "\n".join(out) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.table")
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--out", type=Path, help="write the table here instead of stdout")
    args = parser.parse_args(argv)
    try:
        results = load_results(args.results_dir)
    except (OSError, ValueError) as exc:
        print(f"cannot read results under {args.results_dir}: {exc}", file=sys.stderr)
        return 1
    if not results:
        print(f"no results found under {args.results_dir}", file=sys.stderr)
        return 1
    table = render_table(results)
    if args.out is None:
        print(table, end="")
    else:
        args.out.write_text(table, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
