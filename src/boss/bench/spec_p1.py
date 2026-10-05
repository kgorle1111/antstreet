"""P1 of the rules prompt: score the drafts it made, and run the spec mapper over them.

`score` is free: it reads the drafts that `python -m boss.bench.drafts --prompt term_sheet_v3.md`
saved and runs their checks on the saved `final3` products that failed a hidden check. `map` is
paid: one mapper call per usable draft, under a spend cap. The criteria are in
`bench/spec_truth/P1_CRITERIA.md`, committed before the run; a test pins the numbers below to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from os import environ
from pathlib import Path

from boss import spec
from boss.bench.drafts import CLAIMS_FILE, DRAFT_FILE, SCORED, DraftCell, draft_cell_dir
from boss.bench.spec_eval import Product, kills_products, read_sources
from boss.bench.tasks import BenchTask, load_tasks
from boss.errors import INFRASTRUCTURE
from boss.report import dollars
from boss.roles.base import RoleError
from boss.roles.spec_mapper import SPEC_MAPPER, RuleMap, compare, map_rules
from boss.stats import wilson_interval
from boss.termsheet import CheckSpec
from boss.worker import CLI, worker_env

KILL_RATE = 0.45  # (a) kill rate on the failing products
SUBSET_RATE = 0.40  # (b) kill rate on the non-ASCII subset
WRONG_SHARE = 0.05  # (c) wrong checks over checks
MAX_BAD_DRAFTS = 2  # (d) invalid or failed, of the 17
MEAN_CHECKS = 12  # (e) checks per usable draft
EXPECTED_PRODUCTS = 35
EXPECTED_SUBSET = 16
BASE_KILL, BASE_SUBSET, BASE_WRONG, BASE_CHECKS = (28, 89), (3, 38), (2, 124), 7.8
MAPPER_FILE = "mapper.json"
# The failing hidden checks whose failure is accepting a non-ASCII digit: the subset of (b).
NON_ASCII_CHECKS = {
    "bigdecimal": {"invalid_input"},
    "calc": {"malformed_tokens"},
    "duration": {"parse_decimals"},
    "jsonpointer": {"list_indexes", "set_value_errors"},
    "semver": {"parse_invalid_input"},
}


class P1Error(Exception):
    """An input is missing or is not what the criteria were written for."""


@dataclass(frozen=True, slots=True)
class Failing:
    product: Product
    non_ascii: bool


def failing_products(raw: Path) -> list[Failing]:
    """The `final3` products that failed any hidden check: 19 single and 16 firm, 35 in all."""
    found = []
    for result in sorted((raw / "final3").glob("*/*/rep*/result.json")):
        task, arm, rep = result.parts[-4], result.parts[-3], int(result.parts[-2][3:])
        hidden = json.loads(result.read_text(encoding="utf-8")).get("hidden")
        if not isinstance(hidden, dict):
            continue
        failed = sorted(k for k, v in hidden.items() if v != "passed")
        if not failed:
            continue
        runs = sorted((result.parent / ".boss" / "runs").glob("*/product"))
        path = result.parent / "workspace" if arm == "single" else (runs[0] if runs else None)
        if path is None or not path.is_dir():
            raise P1Error(f"{result.parent}: a failing product without its files")
        found.append(
            Failing(
                Product("final3", task, arm, rep, path, ",".join(failed)),
                bool(set(failed) & NON_ASCII_CHECKS.get(task, set())),
            )
        )
    if len(found) != EXPECTED_PRODUCTS or sum(f.non_ascii for f in found) != EXPECTED_SUBSET:
        raise P1Error(
            f"expected {EXPECTED_PRODUCTS} failing products with {EXPECTED_SUBSET} in the "
            f"non-ASCII subset, found {len(found)} and {sum(f.non_ascii for f in found)}"
        )
    return found


@dataclass(frozen=True, slots=True)
class Draft:
    task: str
    cell: DraftCell
    folder: Path
    idea: str

    @property
    def usable(self) -> bool:
        return self.cell.status == SCORED


def load_drafts(out: Path, tasks: Sequence[BenchTask]) -> list[Draft]:
    """The one draft of each task, or P1Error when a task has none (it was not run)."""
    drafts = []
    for task in tasks:
        folder = draft_cell_dir(out, task.id, 1)
        path = folder / DRAFT_FILE
        if not path.is_file():
            raise P1Error(f"no draft for {task.id}: P1 makes one for each of the 17 tasks")
        drafts.append(Draft(task.id, DraftCell.load(path), folder, task.idea))
    return drafts


@dataclass(frozen=True, slots=True)
class Coverage:
    rules: int
    uncovered: int
    waived: int
    anchored: int
    unanchored: int
    anchor_missing: int
    cited_per_check: float


def coverage_of(draft: Draft) -> Coverage | None:
    """What `boss.spec.verify` says about the draft: None for a draft with no claims saved."""
    claims_path = draft.folder / CLAIMS_FILE
    if not claims_path.is_file():
        return None
    rules = spec.load(draft.folder / spec.RULES_FILE, draft.idea)
    kept = json.loads(claims_path.read_text(encoding="utf-8"))
    claims = {c: tuple(r) for c, r in kept["claims"].items()}
    report = spec.verify(rules, claims, read_sources(draft.folder / "checks"), kept["untested"])
    cited = [len(r) for r in claims.values()]
    return Coverage(
        report.scorable,
        report.count("uncovered"),
        report.count("waived"),
        report.count("anchored"),
        report.count("unanchored"),
        report.count("anchor_missing"),
        sum(cited) / len(cited) if cited else 0.0,
    )


@dataclass(frozen=True, slots=True)
class P1:
    drafts: tuple[Draft, ...]
    pairs: dict[str, dict[str, bool]]  # task -> product key -> killed
    products: tuple[Failing, ...]

    @property
    def usable(self) -> list[Draft]:
        return [d for d in self.drafts if d.usable]

    def killed(self, only_subset: bool = False) -> tuple[int, int]:
        hit = total = 0
        for failing in self.products:
            if only_subset and not failing.non_ascii:
                continue
            row = self.pairs.get(failing.product.task)
            if row is not None and failing.product.key in row:
                total += 1
                hit += row[failing.product.key]
        return hit, total

    @property
    def wrong(self) -> tuple[int, int]:
        scores = [d.cell.score for d in self.usable if d.cell.score]
        return sum(len(s.wrong) for s in scores), sum(s.checks for s in scores)

    @property
    def bad(self) -> int:
        return sum(1 for d in self.drafts if not d.usable)

    @property
    def mean_checks(self) -> float:
        scores = [d.cell.score.checks for d in self.usable if d.cell.score]
        return sum(scores) / len(scores) if scores else 0.0


def _rate(x: tuple[int, int]) -> float:
    return x[0] / x[1] if x[1] else 0.0


def verdicts(p1: P1) -> dict[str, bool]:
    return {
        "a": _rate(p1.killed()) >= KILL_RATE,
        "b": _rate(p1.killed(True)) >= SUBSET_RATE,
        "c": _rate(p1.wrong) <= WRONG_SHARE,
        "d": p1.bad <= MAX_BAD_DRAFTS,
        "e": p1.mean_checks <= MEAN_CHECKS,
    }


def run_score(
    out: Path,
    raw: Path,
    tasks_dir: Path,
    workers: int = 4,
    cache: Path | None = None,
    expected_tasks: int = 17,
) -> P1:
    tasks = [t for t in load_tasks(tasks_dir) if (out / t.id).is_dir()]
    if len(tasks) != expected_tasks:
        raise P1Error(
            f"expected the {expected_tasks} original tasks' drafts under {out}, found {len(tasks)}"
        )
    drafts = load_drafts(out, tasks)
    products = failing_products(raw)
    by_task = {t.id: t for t in tasks}
    saved: dict[str, dict[str, bool]] = {}
    if cache is not None and cache.is_file():
        saved = json.loads(cache.read_text(encoding="utf-8"))

    def work(draft: Draft) -> dict[str, bool]:
        mine = [f.product for f in products if f.product.task == draft.task]
        return kills_products(by_task[draft.task], draft.folder / "checks", mine)

    todo = [d for d in drafts if d.usable and d.task not in saved]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for draft, row in zip(todo, pool.map(work, todo), strict=True):
            saved[draft.task] = row
    if cache is not None:
        cache.write_text(json.dumps(saved, indent=1, sort_keys=True), encoding="utf-8")
    return P1(tuple(drafts), {d.task: saved[d.task] for d in drafts if d.usable}, tuple(products))


def _interval(x: tuple[int, int]) -> str:
    low, high = wilson_interval(*x)
    return f"{x[0]}/{x[1]} = {_rate(x):.0%} [{low:.0%}-{high:.0%}]"


def render(p1: P1) -> str:
    ok = verdicts(p1)
    word = {True: "met", False: "NOT met"}
    spent = sum(d.cell.cost_micros or 0 for d in p1.drafts)
    unknown = sum(1 for d in p1.drafts if d.cell.cost_micros is None)
    lines = [
        "# P1: the rules prompt, draft only",
        "",
        "Criteria: `bench/spec_truth/P1_CRITERIA.md`, committed before any paid call.",
        "",
        "| | Criterion | Result | Baseline | |",
        "|---|---|---|---|---|",
        f"| (a) | kill rate on the failing products >= {KILL_RATE:.0%} | "
        f"{_interval(p1.killed())} | "
        f"{_interval(BASE_KILL)} | {word[ok['a']]} |",
        f"| (b) | kill rate on the non-ASCII subset >= {SUBSET_RATE:.0%} | "
        f"{_interval(p1.killed(True))} | {_interval(BASE_SUBSET)} | {word[ok['b']]} |",
        f"| (c) | wrong checks <= {WRONG_SHARE:.0%} of checks | {p1.wrong[0]}/{p1.wrong[1]} = "
        f"{_rate(p1.wrong):.1%} | 2/124 = 1.6% | {word[ok['c']]} |",
        f"| (d) | invalid or failed drafts <= {MAX_BAD_DRAFTS} of 17 | "
        f"{p1.bad} of {len(p1.drafts)} | "
        f"13 of 17 (staged) | {word[ok['d']]} |",
        f"| (e) | mean checks per usable draft <= {MEAN_CHECKS} | {p1.mean_checks:.1f} | "
        f"{BASE_CHECKS} | {word[ok['e']]} |",
        "",
        f"All five met: **{all(ok.values())}**. P2 is not run by this step.",
        "",
        f"Spend of the drafts, as the cells recorded it: ${spent / 1_000_000:.4f}"
        f"{f' ({unknown} cell(s) with no reported cost)' if unknown else ''}.",
        "",
        "## Per draft",
        "",
        "| task | status | checks | wrong | mutants killed | rules | uncovered | waived | anchored "
        "| unanchored | anchor-missing | cites/check | killed products | cost |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for d in p1.drafts:
        s = d.cell.score
        cov = coverage_of(d) if d.usable else None
        row = p1.pairs.get(d.task, {})
        killed = f"{sum(row.values())}/{len(row)}" if d.usable else "-"
        cost = "unknown" if d.cell.cost_micros is None else dollars(d.cell.cost_micros)
        cells = [
            d.task,
            d.cell.status,
            str(s.checks) if s else "-",
            str(len(s.wrong)) if s else "-",
            f"{len(s.killed)}/{s.mutants}" if s else "-",
            *(
                [str(cov.rules), str(cov.uncovered), str(cov.waived), str(cov.anchored),
                 str(cov.unanchored), str(cov.anchor_missing), f"{cov.cited_per_check:.1f}"]
                if cov
                else ["-"] * 7
            ),
            killed,
            cost,
        ]  # fmt: skip
        lines.append("| " + " | ".join(cells) + " |")
    bad = [d for d in p1.drafts if not d.usable]
    if bad:
        lines += ["", "## Drafts that were not usable", ""]
        lines += [
            f"- {d.task}: {d.cell.status} ({d.cell.outcome}): {d.cell.detail[:300]}" for d in bad
        ]
    return "\n".join(lines) + "\n"


# --- the mapper pass (paid) ---------------------------------------------------------------------


def _saved_charge(path: Path) -> int:
    """What a mapper call saved by an earlier pass counts against the cap: its recorded cost, or the
    call's cap when the file is unrecorded, unreadable or malformed, never zero."""
    if not path.is_file():
        return 0
    try:
        cost = json.loads(path.read_text(encoding="utf-8")).get("cost_micros")
    except (OSError, ValueError, AttributeError):
        cost = None
    return SPEC_MAPPER.cap_micros if not isinstance(cost, int) or isinstance(cost, bool) else cost


def run_mapper(
    out: Path,
    tasks_dir: Path,
    cap_micros: int,
    *,
    environ: Mapping[str, str],
    executable: str = CLI,
) -> tuple[int, int]:
    """One mapper call per usable draft, one at a time, stopping before a call that could take the
    measured spend past `cap_micros`, counting the calls an earlier pass saved. Returns (calls made,
    spend of this pass); saves `mapper.json` by each."""
    tasks = [t for t in load_tasks(tasks_dir) if (out / t.id).is_dir()]
    drafts = load_drafts(out, tasks)
    saved, spent, calls = sum(_saved_charge(d.folder / MAPPER_FILE) for d in drafts), 0, 0
    for draft in drafts:
        path = draft.folder / MAPPER_FILE
        if not draft.usable or path.is_file() or not (draft.folder / CLAIMS_FILE).is_file():
            continue
        if saved + spent + SPEC_MAPPER.cap_micros > cap_micros:
            print(f"Stopped at the cap: ${(saved + spent) / 1e6:.4f} of ${cap_micros / 1e6:.2f}.")
            break
        rules = spec.load(draft.folder / spec.RULES_FILE, draft.idea)
        kept = json.loads((draft.folder / CLAIMS_FILE).read_text(encoding="utf-8"))
        checks = [
            CheckSpec(c, "", f"test_{c}.py", "t1", tuple(r)) for c, r in kept["claims"].items()
        ]
        try:
            mapped, usage = map_rules(
                rules,
                checks,
                draft.folder / "checks",
                env=worker_env(environ),
                model="haiku",
                executable=executable,
            )
            data: dict[str, object] = {
                "status": "ok",
                "exercises": {c: list(v) for c, v in mapped.exercises.items()},
            }
        except RoleError as exc:
            usage = exc.usage
            if exc.outcome in INFRASTRUCTURE:  # says nothing about the mapper: keep nothing, stop
                spent += 0 if usage.cost_micros is None else usage.cost_micros
                print(
                    f"Stopped: the call ended as {exc.outcome}; nothing was saved for {draft.task}."
                )
                break
            data = {"status": "failed", "detail": str(exc)[:500], "outcome": str(exc.outcome)}
        cost = usage.cost_micros
        spent += SPEC_MAPPER.cap_micros if cost is None else cost
        calls += 1
        data["cost_micros"] = cost
        path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        print(f"  {draft.task:<14} {data['status']}  ${(cost or 0) / 1e6:.4f}")
    print(f"Mapper calls {calls}, measured spend ${spent / 1e6:.4f}.")
    return calls, spent


def render_mapper(out: Path, tasks_dir: Path) -> str:
    """The mapper's unconfirmed citations against the verifier's `anchor_missing`, per draft."""
    tasks = [t for t in load_tasks(tasks_dir) if (out / t.id).is_dir()]
    rows, ok, over, both, miss = [], 0, 0, 0, 0
    for draft in load_drafts(out, tasks):
        path = draft.folder / MAPPER_FILE
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["status"] != "ok":
            rows.append(f"| {draft.task} | failed | - | - |")
            continue
        ok += 1
        kept = json.loads((draft.folder / CLAIMS_FILE).read_text(encoding="utf-8"))
        claims = {c: tuple(r) for c, r in kept["claims"].items()}
        mapped = RuleMap(
            {c: tuple((r, int(n)) for r, n in v) for c, v in data["exercises"].items()}
        )
        unconfirmed = {(c, r) for c, r in compare(claims, mapped).overclaims}
        rules = spec.load(draft.folder / spec.RULES_FILE, draft.idea)
        report = spec.verify(rules, claims, read_sources(draft.folder / "checks"), kept["untested"])
        flagged = {
            (c, s.rule) for s in report.statuses if s.state == "anchor_missing" for c in s.checks
        }
        over += len(unconfirmed)
        both += len(unconfirmed & flagged)
        miss += len(flagged)
        rows.append(
            f"| {draft.task} | ok | {len(unconfirmed)} | "
            f"{len(flagged)} ({len(unconfirmed & flagged)} also unconfirmed) |"
        )
    lines = [
        "## Spec mapper pass (reported, no criterion)",
        "",
        f"- {ok} drafts mapped; {over} citations the mapper could not confirm; the verifier "
        f"flagged "
        f"{miss} claims as anchor-missing, {both} of them also unconfirmed by the mapper",
        "",
        "| task | mapper | unconfirmed citations | verifier anchor-missing claims |",
        "|---|---|---|---|",
        *rows,
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.spec_p1", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    score = sub.add_parser("score", help="score the drafts (free)")
    score.add_argument(
        "--raw", type=Path, required=True, help="the saved cells (bench/results/raw)"
    )
    score.add_argument("--cache", type=Path)
    score.add_argument("--workers", type=int, default=4)
    mapper = sub.add_parser("map", help="the mapper over the usable drafts (paid, capped)")
    mapper.add_argument("--max-spend", type=float, required=True, metavar="USD")
    report = sub.add_parser("mapper-report", help="the mapper's results (free)")
    for p in (score, mapper, report):
        p.add_argument(
            "--drafts", type=Path, required=True, help="the drafts folder (--out of drafts)"
        )
        p.add_argument("--tasks", type=Path, default=Path("bench/tasks"))
    args = parser.parse_args(argv)
    try:
        if args.command == "score":
            print(
                render(run_score(args.drafts, args.raw, args.tasks, args.workers, args.cache)),
                end="",
            )
        elif args.command == "map":
            run_mapper(args.drafts, args.tasks, round(args.max_spend * 1_000_000), environ=environ)
        else:
            print(render_mapper(args.drafts, args.tasks), end="")
    except P1Error as exc:
        print(f"spec_p1: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
