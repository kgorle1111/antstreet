"""The fixed KPI scorecard of benchmark results: seven figures per column, one table.

The definitions are fixed (see bench/METHOD.md, "KPIs") and computed only from result files and
ledgers, never from model text. Infrastructure failures say nothing about either arm: they are
left out of every figure and counted beside it. A figure the data cannot give is "n/a" or "not
recorded", never 0.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from boss.bench.results import CellResult, cell_dir, load_results
from boss.bench.table import _counted, _duration, _visible_pass
from boss.kpi import investor_questions, single_said_done
from boss.ledger import Event, LedgerError
from boss.report import dollars
from boss.rundir import RunPaths
from boss.stats import md_table, pct, rate

CellKey = tuple[str, str, int]  # (task, arm, rep)
NOTE = "Intervals are Wilson 95%. Overlapping intervals mean no demonstrated difference."
SETS_WARNING = "WARNING: columns ran different task sets; a difference may be the tasks."


@dataclass(frozen=True, slots=True)
class KpiCard:
    """The counts behind one arm's KPIs. Rates are derived from them when rendered."""

    arm: str
    counted: int  # cells counted: infrastructure failures excluded
    infrastructure: int
    task_sets: tuple[str, ...]  # hashes of the task sets the cells ran against
    tasks: int  # tasks with at least one counted cell
    delivered: int  # counted cells whose every hidden check passed
    said_done: int | None  # counted cells where the system said done; None: not recorded
    false_passes: int | None  # of those, cells that failed a hidden check
    cost_micros: int  # known cost of the counted cells, boss calls included
    unknown_cost_events: int  # events of unknown cost in them, never folded into cost_micros
    delivered_s: float | None  # median wall clock of delivered cells
    counted_s: float | None  # median wall clock of counted cells
    reliable_tasks: int  # tasks delivered on every one of their counted runs
    runs_per_task: tuple[tuple[int, int], ...]  # (k counted runs, tasks with that k), by k
    questions: int  # investor questions over the counted cells with a recorded count
    question_runs: int  # counted cells whose count is recorded
    wrong_checks: int | None  # boss checks the reference solution fails; None: not measured
    boss_checks: int | None  # boss checks in the cells where that was measured


def _said_done(r: CellResult, ledger: Sequence[Event] | None) -> bool | None:
    """Whether the system claimed to be finished: the firm's visible checks all passed and, when
    it had held-out checks, those too; the single arm's final status word was `done`, which its
    result file records, else (older results) its ledger. None with neither."""
    if r.arm == "firm":
        held = r.held_out_total or 0
        return _visible_pass(r) and (not held or r.held_out_passed == held)
    if r.final_status is not None:
        return r.final_status == "done"
    return None if ledger is None else single_said_done(ledger)


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def kpi_card(
    results: Sequence[CellResult], ledgers: Mapping[CellKey, Sequence[Event]] | None = None
) -> KpiCard:
    """The KPI card of one arm's cells; `ledgers` holds the cells' ledgers that exist."""
    arms = {r.arm for r in results}
    if len(arms) != 1:
        raise ValueError(f"a card needs the cells of exactly one arm, got {sorted(arms)}")
    arm = arms.pop()
    ledgers = ledgers or {}
    cells = _counted(results)
    delivered = [r for r in cells if r.passed]

    claims = [(r, _said_done(r, ledgers.get((r.task, r.arm, r.rep)))) for r in cells]
    known = [r for r, said in claims if said is not None]
    said = [r for r, said in claims if said]

    runs = Counter(Counter(r.task for r in cells).values())  # k -> number of tasks with k runs
    tasks = {r.task for r in cells}
    asked = [
        investor_questions(ledgers[k]) for r in cells if (k := (r.task, r.arm, r.rep)) in ledgers
    ]
    measured = [r for r in cells if r.wrong_checks is not None]
    return KpiCard(
        arm=arm,
        counted=len(cells),
        infrastructure=len(results) - len(cells),
        task_sets=tuple(sorted({r.set_hash for r in results})),
        tasks=len(tasks),
        delivered=len(delivered),
        said_done=len(said) if known else None,
        false_passes=sum(not r.passed for r in said) if known else None,
        cost_micros=sum(r.cost_micros for r in cells),
        unknown_cost_events=sum(r.unknown_cost_events for r in cells),
        delivered_s=_median([r.duration_s for r in delivered]),
        counted_s=_median([r.duration_s for r in cells]),
        reliable_tasks=sum(all(r.passed for r in cells if r.task == t) for t in tasks),
        runs_per_task=tuple(sorted(runs.items())),
        # The single arm never asks: 0 by construction, not "not recorded".
        questions=sum(asked) if arm == "firm" else 0,
        question_runs=len(asked) if arm == "firm" else len(cells),
        wrong_checks=sum(r.wrong_checks or 0 for r in measured) if measured else None,
        boss_checks=sum(r.visible_total or 0 for r in measured) if measured else None,
    )


def _delivery(c: KpiCard) -> str:
    out = rate(c.delivered, c.counted, counts="after", empty="n/a (0 cells)")
    return out + (f"; {c.infrastructure} infrastructure excluded" if c.infrastructure else "")


def _false_pass(c: KpiCard) -> str:
    if c.said_done is None or c.false_passes is None:
        return "n/a (the arm's claim is not recorded)"
    return rate(c.false_passes, c.said_done, counts="after", empty="n/a (0 cells that said done)")


def _cost(c: KpiCard) -> str:
    if not c.delivered:
        return "n/a (0 delivered)"
    shown = dollars(round(c.cost_micros / c.delivered))
    return f"{shown} (lower bound)" if c.unknown_cost_events else shown


def _times(c: KpiCard) -> str:
    return f"delivered {_duration(c.delivered_s)}; all counted {_duration(c.counted_s)}"


def _reliability(c: KpiCard) -> str:
    if not c.tasks:
        return "n/a (0 tasks)"
    if len(c.runs_per_task) == 1:
        k = f"k={c.runs_per_task[0][0]}"
    else:
        k = "k varies: " + ", ".join(f"k={k}: {n} task{'s' * (n != 1)}" for k, n in c.runs_per_task)
    return f"{c.reliable_tasks}/{c.tasks} ({k})"


def _questions(c: KpiCard) -> str:
    if c.arm == "single":
        return "0 (the single arm asks none)"
    if not c.question_runs:
        return "not recorded"
    out = f"{c.questions / c.question_runs:.2f} per run ({c.questions} in {c.question_runs} runs)"
    missing = c.counted - c.question_runs
    return out + (f"; {missing} runs not recorded" if missing else "")


def _check_quality(c: KpiCard) -> str:
    if c.arm == "single":
        return "n/a (no boss checks)"
    if c.wrong_checks is None or not c.boss_checks:
        return "not measured"
    return f"{c.wrong_checks}/{c.boss_checks} wrong ({pct(c.wrong_checks / c.boss_checks)})"


def render_cards(columns: Sequence[tuple[str, KpiCard]]) -> str:
    """One table: a row per KPI, a column per labelled card, then the sample sizes."""
    if not columns:
        raise ValueError("cannot render an empty scorecard")
    labels = [label for label, _ in columns]
    if len(set(labels)) != len(labels):
        raise ValueError("two columns carry the same label: " + ", ".join(sorted(labels)))
    rows: list[tuple[str, list[str]]] = [
        ("1 Delivery rate", [_delivery(c) for _, c in columns]),
        ("2 False-pass rate", [_false_pass(c) for _, c in columns]),
        ("3 Cost per delivered task", [_cost(c) for _, c in columns]),
        ("  events of unknown cost", [str(c.unknown_cost_events) for _, c in columns]),
        ("4 Time to delivery (median)", [_times(c) for _, c in columns]),
        ("5 Reliability (pass^k)", [_reliability(c) for _, c in columns]),
        ("6 Investor questions", [_questions(c) for _, c in columns]),
        ("7 Check quality", [_check_quality(c) for _, c in columns]),
    ]
    mixed = len({c.task_sets for _, c in columns}) > 1
    out = [SETS_WARNING, ""] if mixed else []
    out += md_table(["KPI", *labels], [[name, *cells] for name, cells in rows])
    out += ["", "Sample sizes (counted cells over tasks; infrastructure failures excluded):"]
    out += [
        f"  {label}: {c.counted} cells over {c.tasks} tasks ({c.infrastructure} excluded)"
        for label, c in columns
    ]
    return "\n".join([*out, "", NOTE]) + "\n"


def load_ledger(cell: Path) -> list[Event] | None:
    """The cell's ledger: `ledger.jsonl` for the single arm, the run's for the firm arm. None when
    there is not exactly one, or it cannot be read."""
    found = [*cell.glob("ledger.jsonl"), *cell.glob(".boss/runs/*/ledger.jsonl")]
    if len(found) != 1:
        return None
    try:
        return RunPaths(found[0].parent).events()
    except (OSError, LedgerError):
        return None


class _Column(NamedTuple):
    folder: Path
    arm: str
    model: str
    budget: str
    firm_args: str
    set_hash: str  # not in the label: two columns that differ only in it are refused

    @property
    def label(self) -> str:
        extra = f", {self.firm_args}" if self.firm_args else ""
        return f"{self.folder.name}/{self.arm} ({self.model}, {self.budget}{extra})"


def build_columns(folders: Sequence[Path]) -> list[tuple[str, KpiCard]]:
    """One card per folder, arm, model, budget, firm args and task set, labelled by all of them
    but the task set. Raises ValueError when two columns would carry the same label."""
    groups: dict[_Column, list[CellResult]] = {}
    ledgers: dict[_Column, dict[CellKey, list[Event]]] = {}
    for folder in folders:
        for r in load_results(folder):
            column = _Column(
                folder, r.arm, r.model, dollars(r.budget_micros), r.firm_args, r.set_hash
            )
            groups.setdefault(column, []).append(r)
            if (events := load_ledger(cell_dir(folder, r.task, r.arm, r.rep))) is not None:
                ledgers.setdefault(column, {})[(r.task, r.arm, r.rep)] = events
    labels = [c.label for c in groups]
    if len(set(labels)) != len(labels):
        dup = next(label for label in labels if labels.count(label) > 1)
        raise ValueError(
            f"two columns carry the label {dup!r}: they differ only in task set, or two folders "
            "share a name"
        )
    return [(c.label, kpi_card(results, ledgers.get(c))) for c, results in groups.items()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.kpi")
    parser.add_argument("results_dir", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        columns = build_columns(args.results_dir)
    except (OSError, ValueError) as exc:
        print(f"cannot build the scorecard: {exc}", file=sys.stderr)
        return 1
    if not columns:
        print("no results found", file=sys.stderr)
        return 1
    print(render_cards(columns), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
