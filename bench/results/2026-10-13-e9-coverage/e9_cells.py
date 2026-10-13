"""E9's counts that the repo's tools do not print, read from saved cells only (no model call).

    python bench/results/2026-10-13-e9-coverage/e9_cells.py RAW [--subsets OUT]

RAW holds `e9-coverage`, `e9-firm` and `e9-single`. With `--subsets OUT` it also writes folders of
symlinks under OUT, one per model stretch, for `python -m antstreet.bench.paired` and `.kpi`:
`h55/` (the 8 tasks whose 3 coverage cells all ran on Haiku 5.5) and `h45/` (the 26 tasks whose 3
coverage cells all ran on Haiku 4.5); `shortestpath`, split 2 and 1, is in neither. Every file read
is data: a cell's text is counted, never acted on.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import statistics
from pathlib import Path
from typing import Any

ARMS = ("e9-coverage", "e9-firm", "e9-single")
MODEL_RE = re.compile(r'"model":\s*"(claude-[a-z0-9.-]+)"')
# The coverage arm ran in two stretches: up to 2026-10-11 and from 2026-10-13 (UTC run ids).
STRETCH_SPLIT = "20261012"


def cell_facts(cell: Path) -> dict[str, Any]:
    r = json.loads((cell / "result.json").read_text())
    models: set[str] = set()
    for f in glob.glob(f"{cell}/**/*.jsonl", recursive=True, include_hidden=True):
        if not f.endswith("ledger.jsonl"):  # worker logs: the CLI's stream, with the model id
            models |= set(MODEL_RE.findall(Path(f).read_text(errors="replace")))
    events = []
    runs = sorted(glob.glob(f"{cell}/.boss/runs/*"))
    for run in runs:
        led = Path(run) / "ledger.jsonl"
        events += [json.loads(line) for line in led.read_text().splitlines() if line]
    approved = [e["data"] for e in events if e["event"] == "approved"]
    spec = approved[0].get("spec") if approved else None
    cov = None
    for run in runs:
        if (Path(run) / "coverage.json").is_file():
            cov = json.loads((Path(run) / "coverage.json").read_text())
    transcript = cell / "transcript.txt"
    said = transcript.read_text(errors="replace") if transcript.is_file() else ""
    delivered = bool(r["hidden"]) and all(v == "passed" for v in r["hidden"].values())
    visible_all = bool(r["visible_total"]) and r["visible_passed"] == r["visible_total"]
    return {
        "task": r["task"],
        "rep": r["rep"],
        "started": os.path.basename(runs[0]) if runs else "",
        "model": ",".join(sorted(models)) or "none (no worker ran)",
        "delivered": delivered,
        "false_pass": visible_all and not delivered,
        "outcome": r["outcome"],
        "cost": r["cost_micros"] / 1e6,
        "boss_cost": r["boss_micros"] / 1e6,
        "secs": r["duration_s"],
        "checks": r["visible_total"] or 0,
        "boss_calls": [
            (e["data"].get("purpose"), e["data"].get("outcome"), e["cost_micros"], e["tokens_out"])
            for e in events
            if e["event"] == "boss_call"
        ],
        "redrafts": cov["redrafts"] if cov else None,
        "redraft_not_kept": said.count("The redraft has no fewer gaps"),
        "redraft_failed": said.count("The redraft failed"),
        "weak_left": len(cov["weak"]) if cov else None,
        "unmeasured": bool(cov and cov["unmeasured"]),
        "waived_left": len(spec["investor_waived"]) if spec else None,
        "anchor_missing_left": spec["anchor_missing"] if spec else None,
        "hidden": r["hidden"],
        "stops": [e["data"].get("reason", "") for e in events if e["event"] == "stopped"],
    }


def load(raw: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        arm: [cell_facts(p.parent) for p in sorted((raw / arm).glob("*/*/rep*/result.json"))]
        for arm in ARMS
    }


def report(cells: dict[str, list[dict[str, Any]]]) -> None:
    cov = cells["e9-coverage"]
    # A coverage cell whose boss stopped the run has no worker log; its start time says its stretch.
    stretch = {(c["task"], c["rep"]): "4.5" if c["started"] < STRETCH_SPLIT else "5.5" for c in cov}

    def of(c: dict[str, Any]) -> str:  # the stretch of the coverage cell with this (task, rep)
        return stretch[(c["task"], c["rep"])]

    print("== model ids in the worker logs, cells per arm")
    for arm in ARMS:
        print(arm, dict(collections.Counter(c["model"] for c in cells[arm])))
    print("coverage cells by stretch:", dict(collections.Counter(stretch.values())))

    print("\n== per arm, on the (task, rep) pairs of each coverage stretch")
    print(
        "arm stretch cells delivered false_pass/visible_all capped boss_stopped "
        "mean_cost mean_boss_cost median_s mean_visible_checks"
    )
    for arm in ARMS:
        for s in ("4.5", "5.5"):
            cs = [c for c in cells[arm] if of(c) == s]
            visible_all = sum(c["false_pass"] or c["delivered"] for c in cs)
            print(
                arm,
                s,
                len(cs),
                sum(c["delivered"] for c in cs),
                f"{sum(c['false_pass'] for c in cs)}/{visible_all}",
                sum(c["outcome"] == "capped" for c in cs),
                sum(c["outcome"].startswith("boss:") for c in cs),
                f"{statistics.mean(c['cost'] for c in cs):.4f}",
                f"{statistics.mean(c['boss_cost'] for c in cs):.4f}",
                f"{statistics.median(c['secs'] for c in cs):.0f}",
                f"{statistics.mean(c['checks'] for c in cs):.1f}",
            )

    print("\n== outcomes and hidden-check statuses per arm")
    for arm in ARMS:
        statuses = collections.Counter(v for c in cells[arm] for v in c["hidden"].values())
        print(arm, dict(collections.Counter(c["outcome"] for c in cells[arm])), dict(statuses))

    print("\n== boss calls (firm-shaped arms), by stretch and purpose")
    for arm in ("e9-coverage", "e9-firm"):
        calls = collections.defaultdict(list)
        for c in cells[arm]:
            for purpose, outcome, cost, out in c["boss_calls"]:
                calls[(of(c) if arm == "e9-coverage" else "5.5", purpose)].append(
                    (outcome, cost, out)
                )
        for (s, purpose), v in sorted(calls.items()):
            done = [x for x in v if x[0] == "completed"]
            print(
                arm,
                s,
                purpose,
                "calls",
                len(v),
                "not completed",
                dict(collections.Counter(x[0] for x in v if x[0] != "completed")),
                f"mean cost ${statistics.mean(x[1] for x in v) / 1e6:.4f}",
                "median tokens_out of completed",
                statistics.median(x[2] for x in done),
            )

    print("\n== coverage arm: redrafts, and the gaps left at approval")
    asked = sum(c["redrafts"] or 0 for c in cov)
    not_kept = sum(c["redraft_not_kept"] for c in cov)
    failed = sum(c["redraft_failed"] for c in cov)
    print("cells by redrafts asked:", dict(collections.Counter(c["redrafts"] for c in cov)))
    print(
        f"redrafts asked {asked}: kept {asked - not_kept - failed}, "
        f"no fewer gaps {not_kept}, failed {failed}"
    )
    appr = [c for c in cov if c["waived_left"] is not None]
    print("approved cells:", len(appr))
    print(
        "  a rule no check cites (waived by the approval): cells",
        sum(c["waived_left"] > 0 for c in appr),
        "rules",
        sum(c["waived_left"] for c in appr),
    )
    print(
        "  a rule whose checks lack its anchor: cells",
        sum(c["anchor_missing_left"] > 0 for c in appr),
        "rules",
        sum(c["anchor_missing_left"] for c in appr),
    )
    print(
        "  a weak check: cells",
        sum((c["weak_left"] or 0) > 0 for c in appr),
        "checks",
        sum(c["weak_left"] or 0 for c in appr),
    )
    print("  stubs not run:", sum(c["unmeasured"] for c in appr))
    for s in ("4.5", "5.5"):
        for clean in (True, False):
            cs = [
                c
                for c in appr
                if of(c) == s
                and clean
                == (not c["waived_left"] and not c["anchor_missing_left"] and not c["weak_left"])
            ]
            print(
                f"  stretch {s}, gate {'clean' if clean else 'with a gap'} at approval: "
                f"{sum(c['delivered'] for c in cs)}/{len(cs)} delivered"
            )

    print("\n== cells not 'completed'")
    for arm in ARMS:
        for c in cells[arm]:
            if c["outcome"] != "completed":
                print(
                    arm,
                    c["task"],
                    c["rep"],
                    of(c),
                    c["outcome"],
                    "delivered" if c["delivered"] else "failed",
                    "|",
                    "; ".join(s[:80] for s in c["stops"]),
                )

    print("\n== delivered out of 3 by task: coverage, firm, single; coverage minus firm")
    by = {arm: {(c["task"], c["rep"]): c for c in cells[arm]} for arm in ARMS}
    for t in sorted({c["task"] for c in cov}):
        d = [sum(by[arm][(t, r)]["delivered"] for r in (1, 2, 3)) for arm in ARMS]
        reps = "/".join(stretch[(t, r)] for r in (1, 2, 3))
        print(f"{t:13s} {d[0]} {d[1]} {d[2]}  {d[0] - d[1]:+d}  coverage stretch {reps}")

    print("\n== failed coverage cells: stretch, outcome, gaps at approval, hidden checks failed")
    for c in cov:
        if not c["delivered"]:
            failed_checks = sorted(k for k, v in c["hidden"].items() if v != "passed")
            print(
                c["task"],
                c["rep"],
                of(c),
                c["outcome"],
                "redrafts",
                c["redrafts"],
                "waived",
                c["waived_left"],
                "anchor_missing",
                c["anchor_missing_left"],
                "weak",
                c["weak_left"],
                failed_checks,
            )


def subsets(cells: dict[str, list[dict[str, Any]]], raw: Path, out: Path) -> None:
    cov = cells["e9-coverage"]
    per_task = collections.defaultdict(set)
    for c in cov:
        per_task[c["task"]].add("4.5" if c["started"] < STRETCH_SPLIT else "5.5")
    for task, seen in sorted(per_task.items()):
        if len(seen) != 1:
            continue  # split across the two models
        name = "h45" if seen == {"4.5"} else "h55"
        for arm in ARMS:
            link = out / name / arm / task
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.is_symlink():
                link.symlink_to((raw / arm / task).resolve())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", type=Path)
    ap.add_argument("--subsets", type=Path)
    args = ap.parse_args()
    cells = load(args.raw)
    report(cells)
    if args.subsets:
        subsets(cells, args.raw, args.subsets)


if __name__ == "__main__":
    main()
