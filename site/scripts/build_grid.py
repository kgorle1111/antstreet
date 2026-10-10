"""Write site/src/data/grid.json: the 77 visible-pass firm cells of the false-pass audit.

Reads the saved cells under bench/results/raw/ (git-ignored, so this runs on the machine that holds
them) and the audit's case table. tests/test_site_facts.py checks the committed file against the
audit README, so CI needs no raw data.

    python3 -I site/scripts/build_grid.py [RAW_DIR]   # RAW_DIR defaults to bench/results/raw
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "bench" / "results" / "raw"
AUDIT = ROOT / "bench" / "results" / "2026-10-03-false-pass-audit" / "README.md"
OUT = ROOT / "site" / "src" / "data" / "grid.json"
RUNS = {"H": "heldout3", "F": "final3"}
# The audit's "Without those 13" (README: Result): 9 non-ASCII-only cells and 4 type-only cells.
NON_ASCII = {1, 3, 6, 7, 8, 19, 21, 25, 27}
INT_VS_FLOAT = {10, 11, 12, 28}


def cases() -> dict[tuple[str, str, int], tuple[int, str]]:
    """(run, task, rep) -> (case number, what the idea says), from the audit's case table."""
    rows: dict[int, tuple[str, str, int, str]] = {}
    for line in AUDIT.read_text().splitlines():
        m = re.match(r"\| (\d+) \| ([HF]) (\w+) r(\d) \| [^|]+ \| (.+?) \| A \|", line)
        if m:
            n, run, task, rep, idea = m.groups()
            rows[int(n)] = (RUNS[run], task, int(rep), idea)
    for n in sorted(rows):  # "same" and "as #N" point at an earlier row's quote
        run, task, rep, idea = rows[n]
        if idea == "same":
            idea = rows[n - 1][3]
        elif ref := re.match(r"as #(\d+)", idea):
            idea = rows[int(ref.group(1))][3]
        rows[n] = (run, task, rep, idea)
    return {(r, t, p): (n, i) for n, (r, t, p, i) in rows.items()}


def main() -> None:
    table = cases()
    cells = []
    for run in ("heldout3", "final3"):
        for path in sorted(RAW.glob(f"{run}/*/firm/rep*/result.json")):
            r = json.loads(path.read_text())
            visible = r["visible_total"] and r["visible_passed"] == r["visible_total"]
            held = r.get("held_out_total") or 0
            if not visible or (r.get("held_out_passed") or 0) < held:
                continue  # the KPI's "said done": visible checks and any held-out checks passed
            failed = sorted(k for k, v in (r.get("hidden") or {}).items() if v != "passed")
            case, idea = table.get((run, r["task"], r["rep"]), (None, None))
            assert bool(failed) == (case is not None), path
            drop = (
                "non-ascii"
                if case in NON_ASCII
                else "int-vs-float"
                if case in INT_VS_FLOAT
                else None
            )
            cells.append({
                "cell": len(cells), "run": run, "task": r["task"], "rep": r["rep"],
                "false_pass": bool(failed), "strict_drop": drop, "case": case,
                "hidden_failed": failed, "idea": idea,
            })  # fmt: skip
    fp = [c for c in cells if c["false_pass"]]
    assert (len(cells), len(fp)) == (77, 29)
    assert sum(not c["strict_drop"] for c in fp) == 16
    lines = ",\n".join(" " + json.dumps(c, ensure_ascii=False) for c in cells)
    OUT.write_text("[\n" + lines + "\n]\n")  # one cell per line, so a diff names the cell
    print(f"wrote {OUT.relative_to(ROOT)}: {len(cells)} cells, {len(fp)} false passes")


if __name__ == "__main__":
    main()
