"""Evaluate the boss's drafted checks without running a worker.

For each task and repetition the boss drafts checks from the idea; each draft is then scored by
`boss.bench.score` against the task's reference (precision) and mutants (recall). The only spend
is the boss's own drafting call, a few cents; a worker is never started. This is what an
improved boss prompt is measured with.

Hidden checks, the reference and the mutants are read only by the scorer, never shown to the boss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from boss import cli, spec
from boss.bench.results import CellResult, cell_dir, load_results
from boss.bench.score import DraftScore, draft_checks, score_draft
from boss.bench.table import MIXED_WARNING, wilson_interval
from boss.bench.tasks import BenchTask, load_tasks, task_set_hash, validate_task
from boss.boss import (
    DEFAULT_CAP_MICROS,
    DEFAULT_MODEL,
    RULES_PROMPT,
    TERM_SHEET_PROMPT,
    BossError,
    InvalidDraftError,
    draft_term_sheet,
    load_prompt,
)
from boss.errors import Outcome
from boss.report import dollars
from boss.roles.base import RoleError, RoleOutputError, system_prompt
from boss.roles.engineering import SYSTEM_DESIGNER, TESTER, StagedDraftError, draft_staged
from boss.roles.product import PRODUCT_MANAGER, write_stories
from boss.stream import Usage
from boss.worker import CLI, usd, worker_env

DRAFT_FILE = "draft.json"
CLAIMS_FILE = "claims.json"  # a draft made with rules: who cites which rule, and the waivers
REJECTED_FILE = "rejected_output.json"
CHECKS_DIR = "checks"
# The term sheet needs a budget to be valid; it is never spent and the prompt does not mention it.
STAGED = "staged"  # in place of a prompt name: the three-role draft
_STAGED_ROLES = (PRODUCT_MANAGER, SYSTEM_DESIGNER, TESTER)
DRAFT_BUDGET_MICROS = 400_000
SCORED, INVALID, FAILED = "scored", "invalid", "failed"
STATUSES = (SCORED, INVALID, FAILED)
_INT_OR_NONE = (int, type(None))
_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "task": str,
    "rep": int,
    "set_hash": str,
    "prompt": str,
    "prompt_sha": str,
    "boss_model": str,
    "boss_thinking": _INT_OR_NONE,
    "status": str,
    "outcome": str,
    "detail": str,
    "cost_micros": _INT_OR_NONE,
    "tokens_in": int,
    "tokens_out": int,
    "tokens_cached": int,
}


@dataclass(frozen=True, slots=True)
class Settings:
    """What a draft was made with. Drafts made with different settings are never mixed."""

    prompt: str
    prompt_sha: str  # a prompt edited in place under the same name is a different prompt
    boss_model: str
    boss_thinking: int | None


@dataclass(frozen=True, slots=True)
class DraftCell:
    """One boss draft for one task, its cost, and, if it was a usable draft, its score."""

    task: str
    rep: int
    set_hash: str
    prompt: str
    prompt_sha: str
    boss_model: str
    boss_thinking: int | None  # None: the CLI's own default
    status: (
        str  # scored | invalid (paid for, but no valid draft) | failed (no draft: capped, login)
    )
    outcome: str  # the boss call's outcome, e.g. "completed", "capped", "login"
    detail: str  # why a draft is invalid or failed; empty for a scored one
    cost_micros: int | None  # None = unknown, never treated as zero
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    score: DraftScore | None  # set exactly when status is "scored"

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")
        if (self.score is not None) != (self.status == SCORED):
            raise ValueError("a draft has a score exactly when its status is 'scored'")

    @property
    def settings(self) -> Settings:
        return Settings(self.prompt, self.prompt_sha, self.boss_model, self.boss_thinking)

    def save(self, cell: Path) -> None:
        cell.mkdir(parents=True, exist_ok=True)
        raw = asdict(self) | {"score": self.score.to_dict() if self.score else None}
        (cell / DRAFT_FILE).write_text(json.dumps(raw, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> DraftCell:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError name no file
            raise ValueError(f"{path}: not valid JSON: {exc}") from exc
        names = {f.name for f in fields(cls)}
        if not isinstance(raw, dict) or set(raw) != names:
            raise ValueError(f"{path}: fields differ from the draft schema")
        for name, kinds in _FIELD_TYPES.items():
            if isinstance(raw[name], bool) or not isinstance(raw[name], kinds):
                raise ValueError(f"{path}: field {name!r} has the wrong type: {raw[name]!r}")
        try:
            score = None if raw["score"] is None else DraftScore.from_dict(raw["score"])
            return cls(**(raw | {"score": score}))
        except ValueError as exc:
            raise ValueError(f"{path}: {exc}") from exc


def settings_for(prompt: str, boss_model: str, boss_thinking: int | None) -> Settings:
    # The staged draft has no single prompt: its identity is its three roles' whole system
    # prompts, skills included, so editing any of them is a different draft.
    text = "".join(map(system_prompt, _STAGED_ROLES)) if prompt == STAGED else load_prompt(prompt)
    return Settings(
        prompt, hashlib.sha256(text.encode()).hexdigest()[:12], boss_model, boss_thinking
    )


def draft_cell_dir(out: Path, task: str, rep: int) -> Path:
    return out / task / f"rep{rep}"


def save_rejected(cell: Path, exc: BaseException | None) -> None:
    """Keep the output a gate refused, beside the cell. It was paid for, and it is what shows
    whether the model or the gate was wrong; with it a corrected gate can be judged for free."""
    while exc is not None and not isinstance(exc, RoleOutputError):
        exc = exc.__cause__
    if exc is None or exc.data is None:
        return
    cell.mkdir(parents=True, exist_ok=True)
    kept = {"role": exc.role, "problems": exc.problems, "output": exc.data}
    (cell / REJECTED_FILE).write_text(json.dumps(kept, indent=2, sort_keys=True), encoding="utf-8")


def run_draft(
    task: BenchTask,
    rep: int,
    out: Path,
    *,
    environ: Mapping[str, str],
    set_hash: str,
    settings: Settings,
) -> DraftCell:
    """Draft and score one cell, or return its saved result if it already ran."""
    cell = draft_cell_dir(out, task.id, rep)
    if (cell / DRAFT_FILE).is_file():
        return DraftCell.load(cell / DRAFT_FILE)
    checks_dir = cell / CHECKS_DIR
    shutil.rmtree(cell, ignore_errors=True)  # leftovers of a run that died before saving
    try:
        if settings.prompt == STAGED:
            usage = _staged_draft(task, checks_dir, environ, settings)
        else:
            rules = spec.split(task.idea) if settings.prompt == RULES_PROMPT else None
            draft = draft_term_sheet(
                task.idea,
                DRAFT_BUDGET_MICROS,
                checks_dir,
                env=worker_env(environ),
                model=settings.boss_model,
                executable=environ.get(cli.EXECUTABLE_VAR, CLI),
                thinking_tokens=settings.boss_thinking,
                prompt_name=settings.prompt,
                rules=rules,
            )
            usage = draft.usage
            if rules is not None:
                save_claims(cell, rules, draft)
    except BossError as exc:
        # A call that completed but gave nothing usable is the draft's fault; anything else
        # (capped, timeout, login, ...) says nothing about the prompt.
        invalid = isinstance(exc, InvalidDraftError) or exc.outcome is Outcome.COMPLETED
        status = INVALID if invalid else FAILED
        result = _cell(task, rep, set_hash, settings, status, exc.usage, str(exc.outcome), str(exc))
        save_rejected(cell, exc)
    else:
        score = score_draft(task, checks_dir)
        result = _cell(task, rep, set_hash, settings, SCORED, usage, score=score)
    result.save(cell)
    return result


def save_claims(cell: Path, rules: spec.Split, draft: Any) -> None:
    """Keep the rule list and who cites what, beside the checks, so the coverage of a draft can be
    read again without a model."""
    (cell / spec.RULES_FILE).write_text(spec.dumps(rules), encoding="utf-8")
    kept = {
        "claims": {c.id: list(c.criteria) for c in draft.sheet.checks},
        "untested": dict(draft.untested),
    }
    (cell / CLAIMS_FILE).write_text(json.dumps(kept, indent=2, sort_keys=True), encoding="utf-8")


def _staged_draft(
    task: BenchTask, checks_dir: Path, environ: Mapping[str, str], settings: Settings
) -> Usage:
    """Stories, then a design, then checks that must cover every criterion: three calls in
    place of the boss's one. Returns what all of them cost; a failure at any stage raises
    BossError carrying what was paid up to and including it."""
    call: dict[str, Any] = {
        "env": worker_env(environ),
        "model": settings.boss_model,
        "executable": environ.get(cli.EXECUTABLE_VAR, CLI),
        "thinking_tokens": settings.boss_thinking,
    }
    paid: list[Usage] = []
    try:
        stories, used = write_stories(task.idea, **call)
        paid.append(used)
        staged = draft_staged(
            task.idea, DRAFT_BUDGET_MICROS, checks_dir, stories=stories, max_tasks=1, **call
        )
    except RoleError as exc:
        raise BossError(str(exc), exc.outcome, _sum([*paid, exc.usage])) from exc
    except StagedDraftError as exc:
        detail = f"{exc.stage}: " + "; ".join(exc.problems)
        raise BossError(detail, exc.outcome, _sum([*paid, *exc.paid.values()])) from exc
    return _sum([*paid, staged.designer_usage, staged.tester_usage])


def _sum(usages: Sequence[Usage]) -> Usage:
    """Usage of several calls together. One unknown cost makes the total unknown."""
    costs = [u.cost_micros for u in usages]
    return Usage(
        None if None in costs else sum(c for c in costs if c is not None),
        sum(u.tokens_in for u in usages),
        sum(u.tokens_out for u in usages),
        sum(u.tokens_cached for u in usages),
    )


def _cell(
    task: BenchTask,
    rep: int,
    set_hash: str,
    settings: Settings,
    status: str,
    usage: Usage,
    outcome: str = str(Outcome.COMPLETED),
    detail: str = "",
    score: DraftScore | None = None,
) -> DraftCell:
    return DraftCell(
        task=task.id,
        rep=rep,
        set_hash=set_hash,
        prompt=settings.prompt,
        prompt_sha=settings.prompt_sha,
        boss_model=settings.boss_model,
        boss_thinking=settings.boss_thinking,
        status=status,
        outcome=outcome,
        detail=detail,
        cost_micros=usage.cost_micros,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        tokens_cached=usage.tokens_cached,
        score=score,
    )


# --- scoring drafts that boss.bench.run already saved ------------------------------------------


def existing_drafts(
    results_dir: Path, tasks: Sequence[BenchTask], jobs: int = 1
) -> tuple[list[DraftCell], int]:
    """Score the boss's checks kept in each firm cell of a `boss.bench.run` results folder.

    Returns the scored drafts and how many firm cells had no draft to score. Spends nothing.
    """
    by_id = {t.id: t for t in tasks}
    found: list[tuple[BenchTask, CellResult, Path]] = []
    without = 0
    for result in load_results(results_dir):
        if result.arm != "firm" or result.task not in by_id:
            continue
        runs = cell_dir(results_dir, result.task, "firm", result.rep) / cli.RUNS_DIR
        checks = sorted(runs.glob(f"*/{CHECKS_DIR}")) if runs.is_dir() else []
        if len(checks) == 1 and draft_checks(checks[0]):
            found.append((by_id[result.task], result, checks[0]))
        else:
            without += 1

    def score(item: tuple[BenchTask, CellResult, Path]) -> DraftCell:
        task, result, checks = item
        return DraftCell(
            task=task.id,
            rep=result.rep,
            set_hash=result.set_hash,
            prompt="as run",
            prompt_sha="",
            boss_model="as run",
            boss_thinking=None,
            status=SCORED,
            outcome=str(Outcome.COMPLETED),
            detail="",
            cost_micros=result.boss_micros,
            tokens_in=0,
            tokens_out=0,
            tokens_cached=0,
            score=score_draft(task, checks),
        )

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(score, found)), without


# --- the table ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Summary:
    calls: int  # every recorded cell
    drafts: int  # scored drafts: the sample for every rate below
    invalid: int
    failed: int
    checks: int
    wrong_checks: int
    wrong_drafts: int  # drafts with at least one wrong check
    mutants: int
    killed: int  # mutants killed by at least one sound check
    killed_only_by_wrong: int
    perfect_drafts: int  # drafts that killed every mutant
    mean_cost_micros: float | None  # over calls of known cost
    unknown_cost_calls: int

    @property
    def precision(self) -> float:
        return (self.checks - self.wrong_checks) / self.checks if self.checks else 0.0

    @property
    def recall(self) -> float:
        return self.killed / self.mutants if self.mutants else 0.0


def summarize(cells: Sequence[DraftCell]) -> Summary:
    scores = [c.score for c in cells if c.score is not None]
    costs = [c.cost_micros for c in cells if c.cost_micros is not None]
    return Summary(
        calls=len(cells),
        drafts=len(scores),
        invalid=sum(c.status == INVALID for c in cells),
        failed=sum(c.status == FAILED for c in cells),
        checks=sum(s.checks for s in scores),
        wrong_checks=sum(len(s.wrong) for s in scores),
        wrong_drafts=sum(bool(s.wrong) for s in scores),
        mutants=sum(s.mutants for s in scores),
        killed=sum(len(s.killed) for s in scores),
        killed_only_by_wrong=sum(len(s.killed_only_by_wrong) for s in scores),
        perfect_drafts=sum(len(s.killed) == s.mutants for s in scores),
        mean_cost_micros=sum(costs) / len(costs) if costs else None,
        unknown_cost_calls=len(cells) - len(costs),
    )


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _share(successes: int, n: int) -> str:
    """A rate over n > 0 drafts with its Wilson interval."""
    low, high = wilson_interval(successes, n)
    return f"{successes}/{n} = {_pct(successes / n)} [{low * 100:.0f}-{high * 100:.0f}%]"


def _md(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    def line(cells: Sequence[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    return [line(header), line(["---"] * len(header))] + [line(r) for r in rows]


def _values(label: str, values: Sequence[object]) -> str:
    return f"{label}: " + ", ".join(sorted({str(v) for v in values}))


def render_table(cells: Sequence[DraftCell]) -> str:
    if not cells:
        raise ValueError("cannot tabulate an empty result set")
    header = " | ".join(
        [
            _values("Task set", [c.set_hash for c in cells]),
            _values("Prompt", [c.prompt for c in cells]),
            _values("Boss model", [c.boss_model for c in cells]),
            _values(
                "Thinking tokens",
                ["default" if c.boss_thinking is None else c.boss_thinking for c in cells],
            ),
        ]
    )
    mixed = any(
        len({getattr(c, f) for c in cells}) > 1
        for f in ("set_hash", "prompt", "prompt_sha", "boss_model", "boss_thinking")
    )
    s = summarize(cells)
    cost = "n/a" if s.mean_cost_micros is None else dollars(round(s.mean_cost_micros))
    out = [header] + ([MIXED_WARNING] if mixed else []) + [""]
    out += _md(
        ["drafts", "invalid", "failed", "checks/draft", "mean cost/draft", "unknown-cost calls"],
        [
            [
                str(s.drafts),
                str(s.invalid),
                str(s.failed),
                f"{s.checks / s.drafts:.1f}" if s.drafts else "n/a",
                cost,
                str(s.unknown_cost_calls),
            ]
        ],
    )
    if s.drafts:
        out += [
            "",
            "Precision: a correct implementation (the reference) must pass every check.",
            f"- wrong checks: {s.wrong_checks} of {s.checks} failed on the reference "
            f"(precision {_pct(s.precision)})",
            f"- drafts with a wrong check: {_share(s.wrong_drafts, s.drafts)}",
            "",
            "Recall: an incorrect implementation (a mutant) must fail a sound check.",
            f"- mutants killed by sound checks: {s.killed} of {s.mutants} "
            f"(recall {_pct(s.recall)})",
            f"- mutants failing only wrong checks, not counted: {s.killed_only_by_wrong}",
            f"- drafts that kill every mutant: {_share(s.perfect_drafts, s.drafts)}",
        ]
    out += ["", *_md(*_per_task(cells))]
    out += ["", "Drafts that were invalid or failed are excluded from every rate above."]
    return "\n".join(out) + "\n"


def _per_task(cells: Sequence[DraftCell]) -> tuple[list[str], list[list[str]]]:
    rows = []
    for task in sorted({c.task for c in cells}):
        s = summarize([c for c in cells if c.task == task])
        rows.append(
            [
                task,
                str(s.drafts),
                f"{s.wrong_checks}/{s.checks}",
                f"{s.killed}/{s.mutants}",
                f"{s.perfect_drafts}/{s.drafts}",
                str(s.invalid + s.failed),
            ]
        )
    header = ["task", "drafts", "wrong/checks", "killed/mutants", "kill all", "excluded"]
    return header, rows


# --- command line ------------------------------------------------------------------------------


def _resume(
    out: Path, cells: Sequence[tuple[BenchTask, int]], settings: Settings
) -> dict[tuple[str, int], DraftCell]:
    """Finished cells under `out`. Refuses cells drafted with other settings, before any spend."""
    done = {}
    for task, rep in cells:
        path = draft_cell_dir(out, task.id, rep) / DRAFT_FILE
        if not path.is_file():
            continue
        cell = DraftCell.load(path)
        if cell.settings != settings:
            raise ValueError(
                f"{path} was drafted with {cell.settings}, not {settings}; "
                "use a fresh --out to compare prompts or models"
            )
        done[(task.id, rep)] = cell
    return done


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.drafts", description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path("bench/tasks"))
    parser.add_argument("--out", type=Path, help="folder for the drafts and their scores")
    parser.add_argument("--only", nargs="+", help="task ids to draft for (default: all)")
    parser.add_argument("--reps", type=int, default=1, help="drafts per task")
    parser.add_argument("--boss-model", default=DEFAULT_MODEL)
    parser.add_argument("--boss-thinking", type=cli._tokens_arg, help="thinking tokens per draft")
    parser.add_argument(
        "--prompt",
        default=TERM_SHEET_PROMPT,
        help=f"term-sheet prompt file under src/boss/prompts, or '{STAGED}' for the product "
        "manager, system designer and tester in place of the boss's one call",
    )
    parser.add_argument("--jobs", type=int, default=2, help="drafts to make and score at once")
    parser.add_argument(
        "--max-spend",
        type=cli.usd_arg,
        metavar="USD",
        help="stop making drafts before the measured spend, plus one more call at its cap, would "
        "pass this; drafts are then made one at a time. A cost the CLI did not report counts as "
        "the cap",
    )
    parser.add_argument("--dry-run", action="store_true", help="list the drafts and exit")
    parser.add_argument(
        "--score-existing",
        type=Path,
        metavar="DIR",
        help="score the boss drafts saved in a boss.bench.run results folder; spends nothing",
    )
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    if args.score_existing is None and args.out is None:
        parser.error("--out is required unless --score-existing is given")
    if args.reps < 1:
        parser.error("--reps must be at least 1")

    every_task = load_tasks(args.tasks)
    tasks = [t for t in every_task if not args.only or t.id in args.only]
    if not tasks:
        print("no matching tasks", file=sys.stderr)
        return 1
    set_hash = task_set_hash(every_task)

    if args.score_existing is not None:
        try:
            cells, without = existing_drafts(args.score_existing, tasks, args.jobs)
        except (OSError, ValueError) as exc:
            print(f"cannot read results under {args.score_existing}: {exc}", file=sys.stderr)
            return 1
        if not cells:
            print(f"no boss drafts found under {args.score_existing}", file=sys.stderr)
            return 1
        print(render_table(cells), end="")
        print(f"Firm cells with no draft to score: {without}.")
        return 0

    try:
        settings = settings_for(args.prompt, args.boss_model, args.boss_thinking)
    except (OSError, ValueError) as exc:
        print(f"cannot use prompt {args.prompt!r}: {exc}", file=sys.stderr)
        return 1
    plan = [(t, rep) for t in tasks for rep in range(1, args.reps + 1)]
    try:
        done = _resume(args.out, plan, settings)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    todo = [(t, rep) for t, rep in plan if (t.id, rep) not in done]
    staged = settings.prompt == STAGED
    per_draft = sum(r.cap_micros for r in _STAGED_ROLES) if staged else DEFAULT_CAP_MICROS
    measured = "not measured yet" if staged else "past runs averaged about $0.09 each"
    print(
        f"task set {set_hash}: {len(plan)} drafts, {len(todo)} to make, "
        f"up to ${usd(len(todo) * per_draft)} at the per-draft cap ({measured})"
    )
    if args.dry_run:
        for task, rep in plan:
            print(f"  {task.id} rep{rep}{'' if (task.id, rep) in done else ' (to do)'}")
        return 0
    for task in {t.id: t for t, _ in todo}.values():
        validate_task(task)

    def run(cell: tuple[BenchTask, int]) -> DraftCell:
        task, rep = cell
        result = run_draft(
            task, rep, args.out, environ=environ, set_hash=set_hash, settings=settings
        )
        print(f"  {task.id:<14} rep{rep}  {_verdict(result)}")
        return result

    if args.max_spend is None:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(run, todo))
    else:
        results = _run_within(run, todo, args.max_spend, done.values())
    print()
    print(render_table([*done.values(), *results]), end="")
    return 0


def _run_within(
    run: Callable[[tuple[BenchTask, int]], DraftCell],
    todo: Sequence[tuple[BenchTask, int]],
    cap_micros: int,
    earlier: Iterable[DraftCell] = (),
) -> list[DraftCell]:
    """Make the drafts one at a time, and stop before one that could take the measured spend past
    `cap_micros`: the next call may cost up to its own cap. A cost the CLI did not report is
    counted at that cap, never as zero. `earlier` are drafts already made, counted in the spend."""
    spent = sum(_charge(c) for c in earlier)
    results: list[DraftCell] = []
    for item in todo:
        if spent + DEFAULT_CAP_MICROS > cap_micros:
            left = len(todo) - len(results)
            print(
                f"Stopped at the spend cap: {dollars(spent)} spent of {dollars(cap_micros)}; "
                f"{left} draft(s) not made."
            )
            break
        cell = run(item)
        spent += _charge(cell)
        results.append(cell)
    print(f"Measured spend {dollars(spent)} of the {dollars(cap_micros)} cap.")
    return results


def _charge(cell: DraftCell) -> int:
    return DEFAULT_CAP_MICROS if cell.cost_micros is None else cell.cost_micros


def _verdict(cell: DraftCell) -> str:
    cost = "cost unknown" if cell.cost_micros is None else f"{dollars(cell.cost_micros)}"
    if cell.score is None:
        return f"{cell.status} ({cell.outcome})  {cost}"
    s = cell.score
    return (
        f"{s.checks} checks, {len(s.wrong)} wrong, "
        f"{len(s.killed)}/{s.mutants} mutants killed  {cost}"
    )


if __name__ == "__main__":
    sys.exit(main())
