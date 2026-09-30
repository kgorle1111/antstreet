"""Command line: `boss fund`, `boss report`, `boss status`, `boss doctor`.

Exit codes: 0 every check passed (or the command succeeded), 1 stopped or failed, 2 usage error
(argparse, or a budget too small to fund one slice), 3 the round closed without every check
passing.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from boss import __version__
from boss.approval import review_term_sheet
from boss.boss import DEFAULT_MODEL, BossError, InvalidDraftError, draft_term_sheet
from boss.budget import MIN_SLICE_MICROS, RESERVE_MICROS, min_round_budget, plan_rounds
from boss.firm import DEFAULT_SLICE_MICROS, DEFAULT_WORKER_MODEL, FirmConfig, run_firm
from boss.ledger import EventType, LedgerWriter, read_events
from boss.limits import RunLimits
from boss.report import build_report, dollars, render_report
from boss.rule import FiringPolicy
from boss.rundir import Recorder, RunPaths
from boss.runner import run_slice
from boss.stream import Usage
from boss.worker import CLI, IsolationError, billing_mode, usd, worker_env

RUNS_DIR = Path(".boss") / "runs"
EXECUTABLE_VAR = "BOSS_CLAUDE_BIN"  # override the `claude` binary, e.g. for tests
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_INCOMPLETE = 0, 1, 2, 3

Ask = Callable[[str], str]
Say = Callable[[str], None]


def main(
    argv: Sequence[str] | None = None,
    *,
    ask: Ask = input,
    say: Say = print,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    environ = os.environ if environ is None else environ
    project = Path(args.dir).resolve()
    if args.command == "fund":
        return _fund(args, project, environ, ask, say)
    if args.command == "doctor":
        return _doctor(args, project, environ, say)
    return _show(args, project, say)


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=".", help="project folder (default: current)")
    parser = argparse.ArgumentParser(
        prog="boss", description="Fund an idea; an LLM boss runs the firm that builds it."
    )
    parser.add_argument("--version", action="version", version=f"boss {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    fund = sub.add_parser(
        "fund", parents=[common], help="draft a term sheet for an idea, approve it, and build it"
    )
    fund.add_argument("idea", help="what to build, in plain words")
    fund.add_argument(
        "--budget", required=True, type=usd_arg, help="total budget in dollars, e.g. 0.50"
    )
    fund.add_argument("--model", default=DEFAULT_WORKER_MODEL, help="worker model")
    fund.add_argument(
        "--rounds", type=int, default=1, help="funding rounds to split the budget into"
    )
    fund.add_argument(
        "--slice", type=usd_arg, default=DEFAULT_SLICE_MICROS, help="dollars per worker slice"
    )
    fund.add_argument(
        "--reserve",
        type=usd_arg,
        default=RESERVE_MICROS,
        help="dollars held back from every slice cap: what one response of the worker model costs",
    )
    fund.add_argument("--max-tasks", type=int, default=1, help="most tasks the boss may split into")
    fund.add_argument("--max-slices", type=int, default=FiringPolicy().max_slices)
    fund.add_argument("--stall-slices", type=int, default=FiringPolicy().stall_slices)
    fund.add_argument(
        "--max-minutes", type=_minutes_arg, help="stop the run after this much wall-clock time"
    )
    fund.add_argument("--no-firing", action="store_true", help="keep funding stalled workers")
    fund.add_argument("--boss-model", default=DEFAULT_MODEL, help="model for the boss's own calls")
    fund.add_argument(
        "--boss-thinking",
        type=_tokens_arg,
        help="thinking tokens the boss may use per call; 0 turns thinking off (default: the CLI's)",
    )

    for name, text in (
        ("report", "print the board report for a run"),
        ("status", "one-line state of a run"),
    ):
        shown = sub.add_parser(name, parents=[common], help=text)
        shown.add_argument("run", nargs="?", help="run id (default: the latest)")
    doctor = sub.add_parser("doctor", parents=[common], help="check that this machine can run boss")
    doctor.add_argument("--live", action="store_true", help="verify login with one small real call")
    return parser


def usd_arg(text: str) -> int:
    try:
        micros = Decimal(text.lstrip("$")) * 1_000_000
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"{text!r} is not a dollar amount") from None
    if micros <= 0 or micros != micros.to_integral_value():
        raise argparse.ArgumentTypeError("budget must be positive, with at most 6 decimal places")
    return int(micros)


def _minutes_arg(text: str) -> float:
    try:
        minutes = float(text)
    except ValueError:
        minutes = 0.0
    if not 0 < minutes < float("inf"):
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number of minutes")
    return minutes


def _tokens_arg(text: str) -> int:
    if not text.isdecimal():
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of tokens")
    return int(text)


def _fund(
    args: argparse.Namespace, project: Path, environ: Mapping[str, str], ask: Ask, say: Say
) -> int:
    env, executable = worker_env(environ), environ.get(EXECUTABLE_VAR, CLI)
    needed = min_round_budget(args.reserve)
    if args.budget // max(args.rounds, 1) < needed:  # refused before anything is spent
        say(
            f"${usd(args.budget)} over {max(args.rounds, 1)} round(s) cannot fund one worker "
            f"slice: a round needs at least ${usd(needed)} (${usd(args.reserve)} reserve plus a "
            f"${usd(MIN_SLICE_MICROS)} slice). Raise --budget or lower --reserve."
        )
        return EXIT_USAGE
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    paths = RunPaths(project / RUNS_DIR / run_id)
    paths.root.mkdir(parents=True)
    say(f"Run {run_id}: drafting the term sheet...")
    with LedgerWriter(paths.ledger) as ledger:
        record = Recorder(ledger, run_id, round=0)

        def boss_spend(usage: Usage, outcome: str) -> None:
            record(
                "boss",
                EventType.BOSS_CALL,
                cost_micros=usage.cost_micros,
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
                tokens_cached=usage.tokens_cached,
                billing=billing_mode(env),
                data={
                    "purpose": "term_sheet",
                    "model": args.boss_model,
                    "thinking_tokens": args.boss_thinking,
                    "outcome": outcome,
                },
            )

        try:
            draft = draft_term_sheet(
                args.idea,
                args.budget,
                paths.checks,
                env=env,
                model=args.boss_model,
                executable=executable,
                max_tasks=args.max_tasks,
                thinking_tokens=args.boss_thinking,
            )
        except BossError as exc:
            boss_spend(exc.usage, str(exc.outcome))
            record("boss", EventType.STOPPED, data={"reason": str(exc)})
            say(f"The boss could not produce a term sheet: {exc}")
            if isinstance(exc, InvalidDraftError):
                say("\n".join(f"  - {p}" for p in exc.problems))
            return EXIT_FAILED
        boss_spend(draft.usage, "completed")

        drafted = draft.sheet
        if args.rounds > 1:
            rounds = plan_rounds(args.budget, len(drafted.checks), args.rounds)
            drafted = dataclasses.replace(drafted, rounds=rounds)
        sheet = review_term_sheet(
            drafted, paths.checks, paths.root, ledger, run_id, ask=ask, say=say
        )
        if sheet is None:
            return EXIT_FAILED
        say("Approved. Hiring a worker...")
        config = FirmConfig(
            model=args.model,
            slice_micros=args.slice,
            reserve_micros=args.reserve,
            policy=FiringPolicy(stall_slices=args.stall_slices, max_slices=args.max_slices),
            firing=not args.no_firing,
            limits=RunLimits(max_seconds=args.max_minutes * 60 if args.max_minutes else None),
        )
        try:
            outcome = run_firm(
                sheet,
                paths,
                ledger,
                run_id,
                env=env,
                config=config,
                ask=ask,
                say=say,
                slice_runner=functools.partial(run_slice, executable=executable),
            )
        except IsolationError as exc:
            say(f"Stopped: the worker did not start isolated ({exc}). Run `boss doctor`.")
            return EXIT_FAILED

    text = render_report(build_report(read_events(paths.ledger)))
    (paths.root / "report.md").write_text(text, encoding="utf-8")
    say(text)
    if outcome.stopped:
        say(f"Ended early: {outcome.stopped}")
    say(f"Run folder: {paths.root}  (built files: {paths.product})")
    return EXIT_OK if outcome.all_passed else EXIT_INCOMPLETE


def _show(args: argparse.Namespace, project: Path, say: Say) -> int:
    runs = project / RUNS_DIR
    names = sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    run = args.run or (names[-1] if names else None)
    if run is None or run not in names:
        say(
            f"No run {run!r} under {runs}."
            if run
            else f"No runs under {runs}. Start one with `boss fund`."
        )
        return EXIT_FAILED
    events = read_events(RunPaths(runs / run).ledger)
    if not events:
        say(f"Run {run} has an empty ledger.")
        return EXIT_FAILED
    report = build_report(events)
    if args.command == "report":
        say(render_report(report))
        return EXIT_OK
    last = events[-1]
    passed = sum(c.status == "passed" for c in report.checks)
    unknown = report.total.unknown_cost_events
    spend = dollars(report.total.cost_micros) + (f" + {unknown} unknown" if unknown else "")
    say(
        f"{run}: last event {last.actor} {last.event}; "
        f"{passed}/{len(report.checks)} checks passing; spend {spend} estimated"
    )
    return EXIT_OK


def _doctor(args: argparse.Namespace, project: Path, environ: Mapping[str, str], say: Say) -> int:
    from boss.doctor import render_doctor, run_doctor

    checks = run_doctor(
        worker_env(environ), project, live=args.live, executable=environ.get(EXECUTABLE_VAR, CLI)
    )
    say(render_doctor(checks))
    return EXIT_OK if all(c.ok for c in checks) else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
