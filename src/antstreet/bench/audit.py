"""Score the check auditor against the reference solution.

The auditor gives an opinion on each check of a draft: does the idea state what the check
demands? The benchmark knows the answer for a check that is wrong: the task's reference solution
fails it (see `antstreet.bench.score`). So the auditor's flags (`contradicts`, `unsupported`) can be
counted against that truth: true positives, false positives, false negatives, and from them
precision and recall of "flags a wrong check".

The scoring functions are pure. The runner audits saved drafts, from a `antstreet.bench.run` results
folder or a `antstreet.bench.drafts` output folder, one model call per draft, and spends real money
unless `--dry-run`. The auditor stays advisory until these numbers say it is worth its cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Collection, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from antstreet import cli
from antstreet.bench.drafts import (
    CHECKS_DIR,
    DRAFT_FILE,
    SCORED,
    DraftCell,
    save_rejected,
)
from antstreet.bench.results import cell_dir, load_results
from antstreet.bench.score import _wrong_ids, draft_checks
from antstreet.bench.table import MIXED_WARNING
from antstreet.bench.tasks import BenchTask, load_tasks, task_set_hash, validate_task
from antstreet.boss import DEFAULT_MODEL
from antstreet.errors import Outcome
from antstreet.report import dollars
from antstreet.roles.advisory import (
    AUDITOR,
    CONSISTENT,
    DROP,
    KEEP,
    VERDICTS,
    Advice,
    Audit,
    Verdict,
    audit_checks,
)
from antstreet.roles.base import RoleError, RoleOutputError, system_prompt
from antstreet.stats import md_table, pct, rate, wilson_interval
from antstreet.stream import Usage
from antstreet.termsheet import CheckSpec, TermSheet, TermSheetError
from antstreet.worker import CLI, EXECUTABLE_VAR, usd, worker_env

AUDIT_FILE = "audit.json"
AUDITED, REJECTED, FAILED = "audited", "rejected", "failed"
STATUSES = (AUDITED, REJECTED, FAILED)
_TERM_SHEET = "term_sheet.json"
_INT_OR_NONE = (int, type(None))
_FIELD_TYPES: dict[str, type | tuple[type, ...]] = {
    "source": str,
    "task": str,
    "rep": int,
    "set_hash": str,
    "prompt_sha": str,
    "model": str,
    "thinking": _INT_OR_NONE,
    "described": bool,
    "status": str,
    "outcome": str,
    "detail": str,
    "cost_micros": _INT_OR_NONE,
    "tokens_in": int,
    "tokens_out": int,
    "tokens_cached": int,
    "checks": list,
    "verdicts": (list, type(None)),
    "wrong": (list, type(None)),
}


# --- scoring: pure ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuditScore:
    """One audit against the truth. Wrong means: the reference solution fails the check."""

    checks: int
    wrong: int
    flagged: int  # judged contradicts or unsupported
    true_positives: int  # flagged and wrong
    false_positives: int  # flagged, and the reference passes it
    false_negatives: int  # judged consistent, and wrong
    true_negatives: int
    judged: dict[str, int]  # verdict kind -> checks given that verdict
    judged_wrong: dict[str, int]  # verdict kind -> of those, the wrong ones

    def __post_init__(self) -> None:
        if self.true_positives + self.false_positives != self.flagged:
            raise ValueError("true and false positives must add up to the flagged checks")
        if self.true_positives + self.false_negatives != self.wrong:
            raise ValueError("true positives and false negatives must add up to the wrong checks")
        if (
            self.true_positives + self.false_positives + self.false_negatives + self.true_negatives
            != (self.checks)
        ):
            raise ValueError("the four counts must add up to the checks")


def score_audit(wrong: Collection[str], audit: Audit) -> AuditScore:
    """Count an audit's flags against the checks the reference fails. `wrong` is the ids of the
    wrong checks; the audit must cover each check of the draft exactly once."""
    ids = [v.check for v in audit.verdicts]
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("an audit to score needs one verdict per check, and at least one")
    if unknown := set(wrong) - set(ids):
        raise ValueError(f"wrong checks the audit does not cover: {sorted(unknown)}")
    judged = dict.fromkeys(VERDICTS, 0)
    judged_wrong = dict.fromkeys(VERDICTS, 0)
    tp = fp = fn = tn = 0
    for v in audit.verdicts:
        if v.verdict not in judged:
            raise ValueError(f"{v.check}: {v.verdict!r} is not a verdict")
        is_wrong = v.check in wrong
        judged[v.verdict] += 1
        judged_wrong[v.verdict] += is_wrong
        if v.verdict == CONSISTENT:
            fn += is_wrong
            tn += not is_wrong
        else:
            tp += is_wrong
            fp += not is_wrong
    return AuditScore(len(ids), len(set(wrong)), tp + fp, tp, fp, fn, tn, judged, judged_wrong)


def advice_correct(check_is_wrong: bool, advice: Advice) -> bool:
    """Whether the consultant recommended what the truth calls for: drop a check the reference
    fails, keep one it passes."""
    return advice.recommendation == (DROP if check_is_wrong else KEEP)


# --- one audited draft --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Settings:
    """What an audit was made with. Audits made with other settings are never mixed."""

    set_hash: str  # the truth is the reference of this task set
    prompt_sha: str  # the system prompt with its skills: edited in place is a different prompt
    model: str
    thinking: int | None


@dataclass(frozen=True, slots=True)
class Target:
    """A draft to audit: where its checks are and what the auditor may be told about them."""

    source: str  # the results folder's name, so two runs never collide
    task: BenchTask
    rep: int
    checks_dir: Path
    specs: tuple[CheckSpec, ...]
    described: bool  # whether the draft's check descriptions were saved


@dataclass(frozen=True, slots=True)
class AuditCell:
    source: str
    task: str
    rep: int
    set_hash: str
    prompt_sha: str
    model: str
    thinking: int | None
    described: bool
    status: str  # audited | rejected (paid, failed its gate) | failed (no usable call)
    outcome: str
    detail: str  # the gate's problems or the failure; empty for an audited one
    cost_micros: int | None  # None = unknown, never treated as zero
    tokens_in: int
    tokens_out: int
    tokens_cached: int
    checks: tuple[str, ...]  # the draft's check ids
    verdicts: tuple[Verdict, ...] | None  # set exactly when status is "audited"
    wrong: tuple[str, ...] | None  # the truth, set exactly when status is "audited"

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}, got {self.status!r}")
        if (self.verdicts is not None) != (self.status == AUDITED) or (
            (self.wrong is not None) != (self.status == AUDITED)
        ):
            raise ValueError("an audit has verdicts and a truth exactly when it is 'audited'")

    @property
    def settings(self) -> Settings:
        return Settings(self.set_hash, self.prompt_sha, self.model, self.thinking)

    @property
    def score(self) -> AuditScore | None:
        if self.verdicts is None or self.wrong is None:
            return None
        return score_audit(self.wrong, Audit(self.verdicts))

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / AUDIT_FILE).write_text(json.dumps(asdict(self), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> AuditCell:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{path}: not valid JSON: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != {f.name for f in fields(cls)}:
            raise ValueError(f"{path}: fields differ from the audit schema")
        for name, kinds in _FIELD_TYPES.items():
            if (
                isinstance(raw[name], bool)
                and kinds is not bool
                or not isinstance(raw[name], kinds)
            ):
                raise ValueError(f"{path}: field {name!r} has the wrong type: {raw[name]!r}")
        try:
            return cls(
                **raw
                | {
                    "checks": _names(raw["checks"], "checks"),
                    "verdicts": None if raw["verdicts"] is None else _verdicts(raw["verdicts"]),
                    "wrong": None if raw["wrong"] is None else _names(raw["wrong"], "wrong"),
                }
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"{path}: {exc}") from exc


def _names(raw: list[Any], field: str) -> tuple[str, ...]:
    if not all(isinstance(n, str) for n in raw):
        raise ValueError(f"{field} must be a list of names")
    return tuple(raw)


def _verdicts(raw: list[Any]) -> tuple[Verdict, ...]:
    keys = {f.name for f in fields(Verdict)}
    if not all(isinstance(v, dict) and set(v) == keys for v in raw):
        raise ValueError(f"verdicts must be objects with exactly {sorted(keys)}")
    if not all(isinstance(x, str) for v in raw for x in v.values()):
        raise ValueError("verdict fields must be text")
    return tuple(Verdict(**v) for v in raw)


def settings_for(model: str, thinking: int | None, set_hash: str) -> Settings:
    text = system_prompt(AUDITOR)
    return Settings(set_hash, hashlib.sha256(text.encode()).hexdigest()[:12], model, thinking)


def audit_cell_dir(out: Path, source: str, task: str, rep: int) -> Path:
    return out / source / task / f"rep{rep}"


def run_audit(
    target: Target,
    out: Path,
    *,
    environ: Mapping[str, str],
    settings: Settings,
    retry_failed: bool = False,
) -> AuditCell:
    """Audit one draft and score it against the reference, or return its saved result.

    The one model call is the auditor's. The truth costs nothing: the gate runs the reference
    on the draft's checks, in the same sandbox as any check.
    """
    folder = audit_cell_dir(out, target.source, target.task.id, target.rep)
    if (folder / AUDIT_FILE).is_file():
        saved = AuditCell.load(folder / AUDIT_FILE)
        if not (retry_failed and saved.status == FAILED):
            return saved
    ids = tuple(c.id for c in target.specs)
    # The truth first: it costs nothing, and if the gate breaks, no call has been paid for yet.
    wrong = tuple(
        sorted(_wrong_ids(target.task, target.checks_dir, draft_checks(target.checks_dir)))
    )
    try:
        audit, usage = audit_checks(
            target.task.idea,
            target.specs,
            target.checks_dir,
            env=worker_env(environ),
            model=settings.model,
            executable=environ.get(EXECUTABLE_VAR, CLI),
            thinking_tokens=settings.thinking,
        )
    except RoleError as exc:
        # A call that completed but gave nothing usable is the model's fault; anything else
        # (capped, timeout, login, ...) says nothing about the auditor.
        rejected = isinstance(exc, RoleOutputError) or exc.outcome is Outcome.COMPLETED
        detail = "; ".join(exc.problems) if isinstance(exc, RoleOutputError) else str(exc)
        cell = _cell(
            target, settings, ids, REJECTED if rejected else FAILED, exc.usage, detail, exc.outcome
        )
        save_rejected(folder, exc)
    else:
        cell = _cell(target, settings, ids, AUDITED, usage, "", Outcome.COMPLETED, audit, wrong)
    cell.save(folder)
    return cell


def _cell(
    target: Target,
    settings: Settings,
    ids: tuple[str, ...],
    status: str,
    usage: Usage,
    detail: str,
    outcome: Outcome,
    audit: Audit | None = None,
    wrong: tuple[str, ...] | None = None,
) -> AuditCell:
    return AuditCell(
        source=target.source,
        task=target.task.id,
        rep=target.rep,
        set_hash=settings.set_hash,
        prompt_sha=settings.prompt_sha,
        model=settings.model,
        thinking=settings.thinking,
        described=target.described,
        status=status,
        outcome=str(outcome),
        detail=detail,
        cost_micros=usage.cost_micros,
        tokens_in=usage.tokens_in,
        tokens_out=usage.tokens_out,
        tokens_cached=usage.tokens_cached,
        checks=ids,
        verdicts=audit.verdicts if audit else None,
        wrong=wrong,
    )


# --- finding the drafts -------------------------------------------------------------------------


def find_drafts(results_dir: Path, tasks: Sequence[BenchTask]) -> tuple[list[Target], int]:
    """The drafts to audit under a results folder, and how many cells had none.

    Two layouts: an `antstreet.bench.run` folder (each firm cell keeps its draft under `.boss/runs/`
    with the term sheet that describes each check) and an `antstreet.bench.drafts` folder (drafts
    that were scored; their check descriptions were not saved). Spends nothing, runs nothing.
    """
    by_id = {t.id: t for t in tasks}
    source = results_dir.resolve().name
    found: list[Target] = []
    without = 0
    for result in load_results(results_dir):
        if result.arm != "firm" or result.task not in by_id:
            continue
        runs = cell_dir(results_dir, result.task, "firm", result.rep) / cli.RUNS_DIR
        folders = sorted(runs.glob(f"*/{CHECKS_DIR}")) if runs.is_dir() else []
        if len(folders) == 1 and draft_checks(folders[0]):
            found.append(_target(source, by_id[result.task], result.rep, folders[0]))
        else:
            without += 1
    for path in sorted(results_dir.glob(f"*/rep*/{DRAFT_FILE}")):
        cell = DraftCell.load(path)
        if cell.task not in by_id:
            continue
        checks = path.parent / CHECKS_DIR
        if cell.status == SCORED and draft_checks(checks):
            found.append(_target(source, by_id[cell.task], cell.rep, checks, has_sheet=False))
        else:
            without += 1
    return found, without


def _target(
    source: str, task: BenchTask, rep: int, checks_dir: Path, *, has_sheet: bool = True
) -> Target:
    descriptions: dict[str, str] = {}
    sheet = checks_dir.parent / _TERM_SHEET
    if has_sheet:
        try:
            sheet_checks = TermSheet.from_json(sheet.read_text(encoding="utf-8")).checks
            descriptions = {c.id: c.description for c in sheet_checks}
        except (OSError, TermSheetError):
            pass  # the audit goes ahead on code alone; `described` records that
    specs = tuple(
        CheckSpec(c.id, descriptions.get(c.id, ""), c.file, "") for c in draft_checks(checks_dir)
    )
    return Target(source, task, rep, checks_dir, specs, described=bool(descriptions))


# --- the report ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Summary:
    calls: int  # every recorded cell
    audits: int  # audited cells: the sample for every rate below
    rejected: int
    failed: int
    described: int  # audits whose drafts had their check descriptions
    checks: int
    wrong: int
    flagged: int
    true_positives: int
    false_positives: int
    false_negatives: int
    judged: dict[str, int]
    judged_wrong: dict[str, int]
    mean_cost_micros: float | None  # over calls of known cost
    unknown_cost_calls: int


def summarize(cells: Sequence[AuditCell]) -> Summary:
    scores = [s for c in cells if (s := c.score) is not None]
    costs = [c.cost_micros for c in cells if c.cost_micros is not None]
    return Summary(
        calls=len(cells),
        audits=len(scores),
        rejected=sum(c.status == REJECTED for c in cells),
        failed=sum(c.status == FAILED for c in cells),
        described=sum(c.described for c in cells if c.status == AUDITED),
        checks=sum(s.checks for s in scores),
        wrong=sum(s.wrong for s in scores),
        flagged=sum(s.flagged for s in scores),
        true_positives=sum(s.true_positives for s in scores),
        false_positives=sum(s.false_positives for s in scores),
        false_negatives=sum(s.false_negatives for s in scores),
        judged={k: sum(s.judged[k] for s in scores) for k in VERDICTS},
        judged_wrong={k: sum(s.judged_wrong[k] for s in scores) for k in VERDICTS},
        mean_cost_micros=sum(costs) / len(costs) if costs else None,
        unknown_cost_calls=len(cells) - len(costs),
    )


def _share(successes: int, n: int) -> str:
    return rate(successes, n, counts="before", empty="n/a (no cases)")


def support(s: Summary) -> list[str]:
    """What the numbers can and cannot support, in plain sentences."""
    if s.audits == 0:
        return [
            f"No audit produced an opinion ({s.rejected} rejected, {s.failed} failed): "
            "there is nothing to rate."
        ]
    lines = [
        f"Recall rests on {s.wrong} wrong checks and precision on {s.flagged} flags. The "
        "intervals treat every check as independent; the checks of one draft share an idea and "
        "a boss, so the real uncertainty is wider."
    ]
    if s.wrong == 0:
        lines.append("No check was wrong in this sample, so recall cannot be measured at all.")
    elif s.wrong < 30:
        low, high = wilson_interval(s.true_positives, s.wrong)
        lines.append(
            f"With only {s.wrong} wrong checks, recall is a rough figure: its 95% interval is "
            f"{(high - low) * 100:.0f} points wide, and one more or fewer wrong check found "
            f"moves it by {100 / s.wrong:.0f} points. It cannot rank two prompts or models that "
            "differ by less than that."
        )
    base = s.wrong / s.checks if s.checks else 0.0
    per_draft = s.flagged / s.audits if s.audits else 0.0
    lines.append(
        f"Base rate: {pct(base)} of checks are wrong, which is the precision of flagging at "
        f"random. The investor reads every check anyway, so an opinion earns its cost only if "
        f"its flags are far likelier to be wrong than that base rate, at a number of flags per "
        f"draft (now {per_draft:.1f}) the investor will read."
    )
    lines.append(
        "A false positive is a flag on a check the reference passes. Such a check can still "
        "demand something the idea does not state (the reference may happen to do it), which "
        "this ground truth cannot see, so precision here is a lower bound on how often a flag "
        "is right."
    )
    if s.audits - s.described:
        lines.append(
            f"{s.audits - s.described} of {s.audits} audits ran on drafts saved without check "
            "descriptions: the auditor saw the code alone."
        )
    lines.append(
        f"{s.rejected} rejected (paid for, failed the gate) and {s.failed} failed audits are "
        "excluded from every rate; a high rejection rate means those drafts got no opinion."
    )
    lines.append(
        "These numbers cannot support letting the auditor decide anything: it stays advisory."
    )
    return lines


def render_report(cells: Sequence[AuditCell]) -> str:
    if not cells:
        raise ValueError("cannot tabulate an empty result set")
    s = summarize(cells)
    header = " | ".join(
        f"{label}: " + ", ".join(sorted({str(getattr(c, key)) for c in cells}))
        for label, key in (
            ("Task set", "set_hash"),
            ("Prompt", "prompt_sha"),
            ("Model", "model"),
            ("Thinking tokens", "thinking"),
        )
    )
    mixed = len({c.settings for c in cells}) > 1
    cost = "n/a" if s.mean_cost_micros is None else dollars(round(s.mean_cost_micros))
    out = [header] + ([MIXED_WARNING] if mixed else []) + [""]
    out += md_table(
        [
            "calls",
            "audited",
            "rejected",
            "failed",
            "checks/audit",
            "mean cost/audit",
            "unknown-cost",
        ],
        [
            [
                str(s.calls),
                str(s.audits),
                str(s.rejected),
                str(s.failed),
                f"{s.checks / s.audits:.1f}" if s.audits else "n/a",
                cost,
                str(s.unknown_cost_calls),
            ]
        ],
    )
    if s.audits:
        by_kind = {k: (s.judged[k], s.judged_wrong[k]) for k in VERDICTS}
        out += [
            "",
            "Truth: a check is wrong when the task's reference solution fails it. "
            "A flag is a verdict of contradicts or unsupported.",
            f"- checks: {s.checks}, wrong (truth): {s.wrong} ({pct(s.wrong / s.checks)})",
            f"- flagged: {s.flagged} ({s.flagged / s.audits:.1f} per audit)",
            f"- true positives {s.true_positives}, false positives {s.false_positives}, "
            f"false negatives {s.false_negatives}",
            "- precision (flag is a wrong check): " + _share(s.true_positives, s.flagged),
            "- recall (wrong check is flagged): " + _share(s.true_positives, s.wrong),
            "",
            *md_table(
                ["verdict", "checks", "of which wrong", "share wrong", "share of all wrong"],
                [
                    [
                        kind,
                        str(n),
                        str(w),
                        pct(w / n) if n else "n/a",
                        pct(w / s.wrong) if s.wrong else "n/a",
                    ]
                    for kind, (n, w) in by_kind.items()
                ],
            ),
        ]
    out += ["", *md_table(*_per_source(cells))]
    out += ["", "What these numbers can support:", *(f"- {line}" for line in support(s))]
    return "\n".join(out) + "\n"


def _per_source(cells: Sequence[AuditCell]) -> tuple[list[str], list[list[str]]]:
    rows = []
    for source in sorted({c.source for c in cells}):
        s = summarize([c for c in cells if c.source == source])
        rows.append(
            [
                source,
                str(s.audits),
                str(s.checks),
                str(s.wrong),
                str(s.flagged),
                str(s.true_positives),
                str(s.false_positives),
                str(s.false_negatives),
                str(s.rejected + s.failed),
            ]
        )
    header = ["source", "audits", "checks", "wrong", "flagged", "TP", "FP", "FN", "excluded"]
    return header, rows


# --- command line -------------------------------------------------------------------------------


def _resume(
    out: Path, targets: Sequence[Target], settings: Settings, retry_failed: bool
) -> dict[tuple[str, str, int], AuditCell]:
    """Finished cells under `out`. Refuses cells made with other settings, before any spend."""
    done = {}
    for t in targets:
        path = audit_cell_dir(out, t.source, t.task.id, t.rep) / AUDIT_FILE
        if not path.is_file():
            continue
        cell = AuditCell.load(path)
        if cell.settings != settings:
            raise ValueError(
                f"{path} was made with {cell.settings}, not {settings}; "
                "use a fresh --out to compare prompts or models"
            )
        if not (retry_failed and cell.status == FAILED):
            done[(t.source, t.task.id, t.rep)] = cell
    return done


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m antstreet.bench.audit", description=__doc__)
    parser.add_argument(
        "--results",
        type=Path,
        nargs="+",
        required=True,
        metavar="DIR",
        help=(
            "folders of saved drafts: antstreet.bench.run results or antstreet.bench.drafts output"
        ),
    )
    parser.add_argument("--tasks", type=Path, default=Path("bench/tasks"))
    parser.add_argument("--out", type=Path, required=True, help="folder for the audits")
    parser.add_argument("--only", nargs="+", help="task ids to audit (default: all)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking", type=cli._tokens_arg, help="thinking tokens per audit")
    parser.add_argument("--jobs", type=int, default=2, help="audits to make and score at once")
    parser.add_argument("--dry-run", action="store_true", help="list the audits and exit")
    parser.add_argument(
        "--retry-failed", action="store_true", help="audit again the cells that failed to run"
    )
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ
    if len({p.resolve().name for p in args.results}) != len(args.results):
        parser.error("--results folders must have different names")

    every_task = load_tasks(args.tasks)
    tasks = [t for t in every_task if not args.only or t.id in args.only]
    if not tasks:
        print("no matching tasks", file=sys.stderr)
        return 1
    set_hash = task_set_hash(every_task)
    targets: list[Target] = []
    without = 0
    for folder in args.results:
        try:
            found, missing = find_drafts(folder, tasks)
        except (OSError, ValueError) as exc:
            print(f"cannot read drafts under {folder}: {exc}", file=sys.stderr)
            return 1
        targets += found
        without += missing
    if not targets:
        print("no drafts found to audit", file=sys.stderr)
        return 1
    settings = settings_for(args.model, args.thinking, set_hash)
    try:
        done = _resume(args.out, targets, settings, args.retry_failed)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    todo = [t for t in targets if (t.source, t.task.id, t.rep) not in done]
    print(
        f"task set {set_hash}: {len(targets)} drafts, {len(todo)} to audit "
        f"({without} cells had no draft); {len(todo)} calls, up to "
        f"${usd(len(todo) * AUDITOR.cap_micros)} at the per-call cap of "
        f"${usd(AUDITOR.cap_micros)}. "
        "The auditor's real cost per call has not been measured."
    )
    if any(not t.described for t in targets):
        print("Some drafts were saved without check descriptions: the auditor sees code alone.")
    if args.dry_run:
        for t in targets:
            state = "" if (t.source, t.task.id, t.rep) in done else " (to do)"
            print(f"  {t.source}/{t.task.id} rep{t.rep}{state}")
        return 0
    for task in {t.task.id: t.task for t in todo}.values():
        validate_task(task)

    def run(target: Target) -> AuditCell:
        result = run_audit(
            target, args.out, environ=environ, settings=settings, retry_failed=args.retry_failed
        )
        print(f"  {target.source}/{target.task.id:<14} rep{target.rep}  {_verdict(result)}")
        return result

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(run, todo))
    print()
    print(render_report([*done.values(), *results]), end="")
    return 0


def _verdict(cell: AuditCell) -> str:
    cost = "cost unknown" if cell.cost_micros is None else dollars(cell.cost_micros)
    score = cell.score
    if score is None:
        return f"{cell.status} ({cell.outcome})  {cost}"
    return (
        f"{score.checks} checks, {score.wrong} wrong, {score.flagged} flagged "
        f"({score.true_positives} right)  {cost}"
    )


if __name__ == "__main__":
    sys.exit(main())
