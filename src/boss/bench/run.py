"""Run benchmark cells: one task, one arm, one repetition, scored by the hidden checks.

Both arms get the same idea text, model, tools and budget. The single arm is one worker given
the idea. The firm arm is `boss fund` with the term sheet approved automatically, which is the
one place an investor decision is automated; results are labelled as such in the method note.
Hidden checks and the reference solution are never copied into a workspace or a prompt.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from boss import cli
from boss.bench.results import ARMS, CellResult, cell_dir
from boss.bench.score import count_wrong_checks
from boss.bench.tasks import BenchTask, grade_imported, load_tasks, task_set_hash, validate_task
from boss.boss import DEFAULT_MODEL, load_prompt
from boss.errors import INFRASTRUCTURE, Outcome
from boss.firm import DEFAULT_WORKER_MODEL, SLICE_SHARE
from boss.gate import run_gate
from boss.held_out import MAX_HELD_OUT
from boss.kpi import single_final_status
from boss.ledger import Event, EventType, LedgerWriter, read_events, total, totals_by
from boss.report import build_report
from boss.rundir import Recorder, RunPaths
from boss.runner import run_slice
from boss.worker import (
    CLI,
    IsolationError,
    SliceSpec,
    billing_mode,
    clean_status,
    usd,
    worker_env,
)

SOLO_PROMPT = "solo_v2.md"
SELF_REVIEW_PROMPT = "self_review_v1.md"
# `single-review` spends no more than `single`: its one slice cap (SLICE_SHARE of the cell budget)
# is split, the build getting this share and the review the rest.
BUILD_SHARE = 0.75
DEFAULT_ARMS = ("single", "firm")  # `single-review` costs a second slice, so it is asked for
_INFRA_OUTCOMES = {str(o) for o in INFRASTRUCTURE} | {"isolation"}


def run_cell(
    task: BenchTask,
    arm: str,
    rep: int,
    results_dir: Path,
    *,
    environ: Mapping[str, str],
    set_hash: str,
    model: str = DEFAULT_WORKER_MODEL,
    boss_model: str = DEFAULT_MODEL,
    budget_micros: int,
    firm_args: Sequence[str] = (),
    held_out: int = 0,
) -> CellResult:
    """Run one cell, or return its saved result if it already ran.

    `held_out` asks the firm arm for that many held-out checks (`boss fund --held-out N`, added to
    `firm_args`, so the result records it); the single arm ignores it.
    """
    if type(held_out) is not int or not 0 <= held_out <= MAX_HELD_OUT:
        raise ValueError(
            f"held_out must be a whole number from 0 to {MAX_HELD_OUT}, got {held_out!r}"
        )
    if arm == "firm" and held_out:
        firm_args = [*firm_args, "--held-out", str(held_out)]
    out = cell_dir(results_dir, task.id, arm, rep)
    if (out / "result.json").is_file():
        return CellResult.load(out / "result.json")
    if out.is_dir() and any(out.iterdir()):  # a cut-off run's ledger would be read as this cell's
        raise RuntimeError(
            f"{out} holds a run cut off before its result; move the folder aside and run again"
        )
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    wrong_checks = None
    held_out_passed = held_out_total = held_out_wrong = None
    if arm == "single":
        workspace, events = _run_single(task, out, environ, model, budget_micros)
    elif arm == "single-review":
        workspace, events = _run_single_review(task, out, environ, model, budget_micros)
    else:
        workspace, events = _run_firm(
            task, out, environ, model, boss_model, budget_micros, firm_args
        )
        if not task.imported:  # no reference solution to judge the boss's checks against
            wrong_checks = count_wrong_checks(task, workspace.parent / "checks")
        held_out_passed, held_out_total = _held_out_counts(events)
        held_out_wrong = count_wrong_checks(task, workspace.parent / "held_out")

    hidden = _score(task, workspace)
    passed = all(status == "passed" for status in hidden.values())
    outcome = _outcome(events)
    closed = next((e for e in reversed(events) if e.event is EventType.ROUND_CLOSED), None)
    spend = total(events)
    failure = None
    if not passed:
        infra = outcome.removeprefix("boss:") in _INFRA_OUTCOMES
        failure = "infrastructure" if infra else "unlabelled"
    result = CellResult(
        task=task.id,
        arm=arm,
        rep=rep,
        set_hash=set_hash,
        model=model,
        budget_micros=budget_micros,
        hidden=hidden,
        visible_passed=closed.data["passed"] if closed else None,
        visible_total=closed.data["total"] if closed else None,
        cost_micros=spend.cost_micros,
        boss_micros=totals_by(events, lambda e: e.actor).get("boss", total([])).cost_micros,
        unknown_cost_events=spend.unknown_cost_events,
        outcome=outcome,
        failure_class=failure,
        duration_s=round(time.monotonic() - start, 1),
        firm_args=" ".join(firm_args) if arm == "firm" else "",
        wrong_checks=wrong_checks,
        held_out_passed=held_out_passed,
        held_out_total=held_out_total,
        held_out_wrong=held_out_wrong,
        final_status=None if arm == "firm" else single_final_status(events),
    )
    result.save(out)
    return result


def slice_caps(budget_micros: int, review: bool) -> list[int]:
    """Caps of the single agent's slices; they sum to at most SLICE_SHARE of the cell budget."""
    total = max(1, int(budget_micros * SLICE_SHARE))
    if not review:
        return [total]
    build = int(total * BUILD_SHARE)
    if build < 1 or total - build < 1:
        raise ValueError(f"budget {budget_micros} is too small to split into two slices")
    return [build, total - build]


def _run_single(
    task: BenchTask, out: Path, environ: Mapping[str, str], model: str, budget_micros: int
) -> tuple[Path, list[Event]]:
    return _run_slices(task, out, environ, model, budget_micros, review=False)


def _run_single_review(
    task: BenchTask, out: Path, environ: Mapping[str, str], model: str, budget_micros: int
) -> tuple[Path, list[Event]]:
    return _run_slices(task, out, environ, model, budget_micros, review=True)


def _run_slices(
    task: BenchTask,
    out: Path,
    environ: Mapping[str, str],
    model: str,
    budget_micros: int,
    *,
    review: bool,
) -> tuple[Path, list[Event]]:
    """The single agent's build slice and, for `review`, one resume of the same session that asks
    it to review its own work. The review runs only after a build that ended normally or at its
    cap; any other end stands as the cell's outcome."""
    env = worker_env(environ)
    workspace = out / "workspace"
    workspace.mkdir(exist_ok=True)
    session = uuid.uuid4()
    caps = slice_caps(budget_micros, review)
    prompts = [f"Build this:\n\n{task.idea}\n\nWhen you stop, report your status."]
    if review:
        prompts.append(load_prompt(SELF_REVIEW_PROMPT).strip())
    solo = load_prompt(SOLO_PROMPT)
    specs = [
        SliceSpec(
            session_id=session,
            resume=n > 0,
            prompt=prompt,
            model=model,
            cap_micros=cap,
            append_system_prompt=solo,
        )
        for n, (prompt, cap) in enumerate(zip(prompts, caps, strict=True))
    ]
    ledger_path = out / "ledger.jsonl"
    with LedgerWriter(ledger_path) as ledger:
        record = Recorder(ledger, f"bench-{task.id}", round=1)
        for n, spec in enumerate(specs, 1):
            start = {"slice": n, "cap_micros": spec.cap_micros, "session": str(spec.session_id)}
            record("worker:solo", EventType.SLICE_START, data=start)
            try:
                run = run_slice(
                    spec,
                    workspace,
                    out / "logs" / "solo.jsonl",
                    env=env,
                    executable=environ.get(cli.EXECUTABLE_VAR, CLI),
                )
            except IsolationError as exc:
                record(
                    "worker:solo", EventType.ERROR, cost_micros=None, data={"isolation": str(exc)}
                )
                break
            record(
                "worker:solo",
                EventType.SLICE_END,
                cost_micros=run.usage.cost_micros,
                tokens_in=run.usage.tokens_in,
                tokens_out=run.usage.tokens_out,
                tokens_cached=run.usage.tokens_cached,
                billing=billing_mode(env),
                # The same cleaning as the firm arm: a worker's words are model output.
                data={"slice": n, "outcome": str(run.outcome), "status": clean_status(run.status)},
            )
            if run.outcome not in (Outcome.COMPLETED, Outcome.CAPPED):
                break
    return workspace, read_events(ledger_path)


def _run_firm(
    task: BenchTask,
    out: Path,
    environ: Mapping[str, str],
    model: str,
    boss_model: str,
    budget_micros: int,
    firm_args: Sequence[str],
) -> tuple[Path, list[Event]]:
    transcript: list[str] = []
    argv = ["fund", task.idea, "--budget", usd(budget_micros), "--model", model]
    argv += ["--boss-model", boss_model, "--dir", str(out), *firm_args]
    cli.main(argv, ask=lambda prompt: "a", say=transcript.append, environ=environ)
    (out / "transcript.txt").write_text("\n".join(transcript), encoding="utf-8")
    [run_dir] = sorted((out / cli.RUNS_DIR).iterdir())
    return RunPaths(run_dir).product, read_events(run_dir / "ledger.jsonl")


def _held_out_counts(events: Sequence[Event]) -> tuple[int | None, int | None]:
    """Held-out checks the product passed, out of those the investor approved; (None, None) for a
    run that had none. One the run did not get to grade counts as not passed."""
    if not events:
        return None, None
    report = build_report(list(events))
    total_checks = max(report.held_out_written, len(report.held_out))
    if not total_checks:
        return None, None
    return sum(c.status == "passed" for c in report.held_out), total_checks


def _score(task: BenchTask, workspace: Path) -> dict[str, str]:
    if task.imported:
        return grade_imported(task, workspace)
    checks = task.hidden_checks()
    if not workspace.is_dir():
        return {c.id: "failed" for c in checks}
    return {r.check_id: str(r.status) for r in run_gate(workspace, task.hidden_dir, checks)}


def _outcome(events: Sequence[Event]) -> str:
    """The worker's outcome, or why no worker finished a slice. A run that paused for the plan
    limit says nothing about either arm, so it is an infrastructure outcome."""
    if any(event.event is EventType.PAUSED for event in events):
        return str(Outcome.USAGE_LIMIT)
    for event in reversed(events):
        if event.event is EventType.SLICE_END:
            return str(event.data.get("outcome", "unknown"))
        if event.event is EventType.ERROR and "isolation" in event.data:
            return "isolation"
    for event in reversed(events):
        if event.event is EventType.BOSS_CALL:
            return f"boss:{event.data.get('outcome', 'unknown')}"
    return "no_events"


def main(argv: Sequence[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.run", description=__doc__)
    parser.add_argument("--tasks", type=Path, default=Path("bench/tasks"))
    parser.add_argument("--out", type=Path, required=True, help="results folder for this run")
    parser.add_argument("--arms", nargs="+", choices=ARMS, default=list(DEFAULT_ARMS))
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--budget", type=cli.usd_arg, required=True, help="dollars per cell")
    parser.add_argument("--model", default=DEFAULT_WORKER_MODEL)
    parser.add_argument("--boss-model", default=DEFAULT_MODEL)
    parser.add_argument("--only", nargs="+", help="task ids to run (default: all)")
    parser.add_argument(
        "--firm-args", default="", help="extra `boss fund` options for the firm arm, quoted"
    )
    parser.add_argument(
        "--held-out",
        type=int,
        choices=range(MAX_HELD_OUT + 1),
        default=0,
        help="held-out checks for the firm arm to ask the examiner for (0 is off)",
    )
    parser.add_argument("--jobs", type=int, default=2, help="cells to run at once")
    parser.add_argument("--dry-run", action="store_true", help="list the cells and exit")
    args = parser.parse_args(argv)
    environ = os.environ if environ is None else environ

    every_task = load_tasks(args.tasks)
    set_hash = task_set_hash(every_task)
    tasks = [t for t in every_task if not args.only or t.id in args.only]
    if not tasks:
        print("no matching tasks", file=sys.stderr)
        return 1
    cells = [(t, arm, rep) for t in tasks for arm in args.arms for rep in range(1, args.reps + 1)]
    ceiling = usd(args.budget * len(cells))
    print(f"task set {set_hash}: {len(cells)} cells, up to ${ceiling} of budget plus boss calls")
    if args.dry_run:
        for task, arm, rep in cells:
            print(f"  {task.id} {arm} rep{rep}")
        return 0
    for task in tasks:
        validate_task(task)

    def run(cell: tuple[BenchTask, str, int]) -> CellResult:
        task, arm, rep = cell
        result = run_cell(
            task,
            arm,
            rep,
            args.out,
            environ=environ,
            set_hash=set_hash,
            model=args.model,
            boss_model=args.boss_model,
            budget_micros=args.budget,
            firm_args=shlex.split(args.firm_args),
            held_out=args.held_out,
        )
        verdict = "PASS" if result.passed else f"fail ({result.failure_class})"
        score = f"{result.hidden_passed}/{result.hidden_total} hidden"
        if result.held_out_total is not None:
            score += f", {result.held_out_passed}/{result.held_out_total} held-out"
        cost = f"${usd(result.cost_micros)}"
        print(f"  {task.id:<14} {arm:<6} rep{rep}  {score}  {cost}  {result.outcome}  {verdict}")
        return result

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results = list(pool.map(run, cells))
    print(f"{sum(r.passed for r in results)}/{len(results)} cells passed every hidden check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
