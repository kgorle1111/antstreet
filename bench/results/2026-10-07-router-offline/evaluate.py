"""Offline evaluation of the cascade's start-tier router on saved benchmark cells. No model call.

Run from the repository root (the raw cells are git-ignored, so pass their folder):

    uv run python bench/results/2026-10-07-router-offline/evaluate.py bench/results/raw

Only firm cells whose ledger, term sheet and checks the cell's investor key vouches for are read
(`routing._verified_attempts`, the production reader). The router is called exactly as `boss fund
--dispatch cascade` calls it, on the cell's own term sheet. `meta.json`'s difficulty is read here,
in the benchmark, only to stratify the report; it is never passed to the router.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from antstreet import routing
from antstreet.termsheet import TermSheet

SETS = ("blind-orig17", "blind-new18", "new18", "e3-base", "e3-par")
SONNET_RATIO = 3  # budget.py's price ratio: a Sonnet attempt on the same tokens costs 3x Haiku's
CLASSIFIER_MICROS = 2_000  # one Haiku classification call, the design's estimate


@dataclass(frozen=True)
class Cell:
    set: str
    task: str
    rep: int
    difficulty: str  # bench only: stratification, never a router input
    delivered: bool  # every hidden check passed
    visible_ok: bool  # every visible check passed
    boss: int
    cost: int
    fresh_cost: int  # the first Haiku worker's cost; 0 if it reached no verdict
    fresh_fail: bool  # the gate fired the first worker for no progress or a slice limit
    verdict: bool  # the first worker reached a verdict the cascade could act on
    start: dict[str, object]  # the router's record, cold start
    kind: str


def load(raw: Path, bench: Path) -> list[Cell]:
    cells = []
    for name in SETS:
        for result in sorted((raw / name).glob("*/firm/rep*/result.json")):
            r = json.loads(result.read_text())
            run = next((result.parent / ".boss" / "runs").glob("*"), None)
            if run is None:
                continue
            try:
                attempts = routing._verified_attempts(run)
            except (ValueError, OSError):
                continue
            sheet = TermSheet.from_json((run / "term_sheet.json").read_text())
            folder = "tasks-multi" if name.startswith("e3") else "tasks"
            meta = json.loads((bench / folder / r["task"] / "meta.json").read_text())
            fresh = [a for a in attempts if not a.retry]
            starts = routing.starts_for(
                sheet, routing.Stats(), top="opus", fundable=lambda _t: True
            )
            hidden = r.get("hidden") or {}
            cells.append(
                Cell(
                    name,
                    r["task"],
                    r["rep"],
                    meta.get("difficulty", "-"),
                    bool(hidden) and all(v == "passed" for v in hidden.values()),
                    r["visible_passed"] == r["visible_total"],
                    r["boss_micros"],
                    r["cost_micros"],
                    sum(a.cost_micros for a in fresh),
                    any(a.failed for a in fresh),
                    bool(fresh),
                    starts[sheet.tasks[0].id].record("opus"),
                    routing.task_kind(sheet, sheet.tasks[0]),
                )
            )
    return cells


def wilson(k: int, n: int) -> str:
    if not n:
        return "n/a"
    z, p = 1.96, k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return f"{k}/{n} = {p:.1%} [{max(0, mid - half):.1%}, {min(1, mid + half):.1%}]"


def per_delivered(cost: float, delivered: float) -> str:
    return f"${cost / delivered / 1e6:.3f}" if delivered else "n/a"


def main(raw: Path) -> None:
    bench = Path(__file__).resolve().parents[2]
    cells = load(raw, bench)
    n = len(cells)
    print(f"Cells: {n} verified firm cells, Haiku boss and workers ({', '.join(SETS)})\n")

    print("## Labels (what a Haiku-only benchmark can observe)")
    deliv = [c for c in cells if c.delivered]
    gate = [c for c in cells if c.fresh_fail]
    label: dict[str, int] = defaultdict(int)
    for c in cells:
        label[
            "delivered"
            if c.delivered
            else "gate fired the first worker"
            if c.fresh_fail
            else "hidden check failed, every visible one passed (gate blind)"
            if c.visible_ok
            else "visible check failed, first worker reached no verdict (budget/rounds ran out)"
            if not c.verdict
            else "visible check failed after a verdict"
        ] += 1
    print(
        f"- Haiku delivered (cheapest delivering tier = haiku, observed): {wilson(len(deliv), n)}"
    )
    print(f"- first Haiku worker fired by the gate (cascade would climb): {wilson(len(gate), n)}")
    fresh_n = sum(c.verdict for c in cells)
    print(f"  as a rate per first worker with a verdict: {wilson(len(gate), fresh_n)}")
    for name, count in sorted(label.items()):
        print(f"- partition: {name}: {count}")
    print(
        "- cheapest delivering tier for the "
        f"{n - len(deliv)} cells Haiku did not deliver: NOT OBSERVED "
        "(no Sonnet or Opus cell exists)\n"
    )

    print("## Router decisions (cold start, production code path)")
    picks: dict[tuple[object, object], int] = defaultdict(int)
    for c in cells:
        picks[(c.start["tier"], c.start["effort"])] += 1
    print(f"- {dict(picks)}")
    print(f"- example reason: {cells[0].start['why']}")
    print(
        f"- agreement with the observed outcome: {len(deliv)}/{n} cells Haiku delivered (start "
        f"right); {len(gate)} Haiku gate failures (a Sonnet start would have saved the Haiku "
        f"attempt); {n - len(deliv) - len(gate)} unobservable\n"
    )

    print("## Replay with pooled history (leave-one-task-out, B105)")
    by_task: dict[str, list[routing.Attempt]] = defaultdict(list)
    for c in cells:
        if c.verdict:
            by_task[c.task].append(
                routing.Attempt(c.kind, False, "haiku", c.fresh_fail, c.fresh_cost)
            )
    replay: dict[str, int] = defaultdict(int)
    for c in cells:
        others = tuple(a for t, v in by_task.items() if t != c.task for a in v)
        choice = routing.choose_start(routing.Stats(others), c.kind, top="opus")
        replay[f"{choice.tier} ({choice.source.split(',')[0]})"] += 1
    print(f"- {dict(replay)}\n")

    print("## Haiku gate-failure rate by pre-build feature (router inputs) and by difficulty")
    feats = {
        "kind": lambda c: c.kind,
        "idea_chars": lambda c: _tercile(c, cells),
        "tasks": lambda c: str(c.start["features"]["tasks"]),  # type: ignore[index]
        "difficulty (bench only)": lambda c: c.difficulty,
    }
    for name, key in feats.items():
        groups: dict[str, list[Cell]] = defaultdict(list)
        for c in cells:
            groups[key(c)].append(c)
        for g, members in sorted(groups.items()):
            v = [c for c in members if c.verdict]
            gf = sum(c.fresh_fail for c in v)
            dl = sum(c.delivered for c in members)
            print(
                f"- {name} {g}: gate fail {wilson(gf, len(v))}; "
                f"delivered {wilson(dl, len(members))}"
            )
    print()

    print("## Expected cost per delivered task (boss call included; Sonnet = 3x Haiku tokens)")
    base_cost = sum(c.cost for c in cells)
    print(
        f"- observed Haiku cells: {per_delivered(base_cost, len(deliv))} ({len(deliv)} delivered)"
    )
    climb_extra = sum(SONNET_RATIO * c.fresh_cost for c in gate)
    print(
        "  Haiku-start cascade = router (identical picks): each gate failure adds one Sonnet rung"
    )
    print("  at 3x that cell's first-worker cost; r = share of those the Sonnet rung rescues.")
    print("  Always Sonnet: boss + 3x the observed worker cost; h = share of the cells Haiku")
    print("  missed that Sonnet delivers (assumed to deliver everything Haiku did).")
    sonnet_cost = sum(c.boss + SONNET_RATIO * (c.cost - c.boss) for c in cells)
    missed = n - len(deliv)
    gate_missed = sum(not c.delivered for c in gate)
    for r in (0.0, 0.5, 1.0):
        haiku = per_delivered(base_cost + climb_extra, len(deliv) + r * gate_missed)
        print(f"- r={r:.1f}: Haiku start / router {haiku}")
    for h in (0.0, 0.25, 0.5, 1.0):
        print(f"- h={h:.2f}: always Sonnet {per_delivered(sonnet_cost, len(deliv) + h * missed)}")
    best_haiku = (base_cost + climb_extra) / (len(deliv) + gate_missed)
    worker = sum(c.cost - c.boss for c in cells)
    boss = sum(c.boss for c in cells)
    k = (best_haiku * n - boss) / (SONNET_RATIO * worker)
    print(
        f"- always Sonnet ties Haiku start (best case r=1) only if it delivers every cell AND uses "
        f"at most {k:.0%} of Haiku's tokens"
    )
    print(
        "- break-even h for a Sonnet start on a subset only (Haiku start at r=1 on the same cells):"
    )
    subsets = {
        "all": cells,
        "idea_chars top tercile": [c for c in cells if _tercile(c, cells).startswith("3")],
        "files=2-3": [c for c in cells if c.kind.startswith("files=2-3")],
    }
    for name, sub in subsets.items():
        d = sum(c.delivered for c in sub)
        g = [c for c in sub if c.fresh_fail]
        h_cost = sum(c.cost for c in sub) + sum(SONNET_RATIO * c.fresh_cost for c in g)
        h_deliv = d + sum(not c.delivered for c in g)
        s_cost = sum(c.boss + SONNET_RATIO * (c.cost - c.boss) for c in sub)
        need = (s_cost * h_deliv / h_cost - d) / (len(sub) - d)
        print(
            f"  {name} ({len(sub)} cells, Haiku delivered {d}): Sonnet must deliver "
            f"{need:.0%} of the {len(sub) - d} Haiku missed" + (" (impossible)" if need > 1 else "")
        )
    oracle = sum(c.fresh_cost for c in gate) / n
    print(
        f"- an oracle that starts Sonnet exactly on the gate failures saves ${oracle / 1e6:.4f} a "
        f"cell; a ${CLASSIFIER_MICROS / 1e6:.3f} classifier call costs more than "
        f"{CLASSIFIER_MICROS / oracle:.0%} of the most it could save"
    )


def _tercile(c: Cell, cells: list[Cell]) -> str:
    sizes = sorted(int(x.start["features"]["idea_chars"]) for x in cells)  # type: ignore[index]
    lo, hi = sizes[len(sizes) // 3], sizes[2 * len(sizes) // 3]
    v = int(c.start["features"]["idea_chars"])  # type: ignore[index]
    return f"1 <{lo}" if v < lo else f"3 >={hi}" if v >= hi else f"2 {lo}-{hi - 1}"


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("bench/results/raw"))
