"""Command line: `boss fund`, `boss resume`, `boss report`, `boss status`, `boss doctor`.

Exit codes:
  0    every required check passes on the product (or the command succeeded)
  1    nothing was built: no usable term sheet, the investor rejected it, a worker did not start
       isolated, the approved checks changed, or the run cannot be read
  2    usage error: a bad option, a blank idea, or a budget too small to fund one slice
  3    the run ended with a check still failing, for any reason (out of budget, a limit, a pause,
       a declined round, a task set aside)
  130  interrupted; continue with `boss resume`
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import sys
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from boss import __version__
from boss.approval import NotApprovedError, review_term_sheet
from boss.boss import DEFAULT_MODEL, BossError, InvalidDraftError, draft_term_sheet
from boss.budget import MIN_SLICE_MICROS, RESERVE_MICROS, min_round_budget, plan_rounds
from boss.firm import (
    DEFAULT_SLICE_MICROS,
    DEFAULT_WORKER_MODEL,
    FirmConfig,
    FirmReport,
    run_firm,
    started_config,
)
from boss.ledger import (
    EventType,
    LedgerCorruptError,
    LedgerLockedError,
    LedgerWriter,
    read_events,
    repair_torn_tail,
)
from boss.limits import RunLimits
from boss.report import build_report, dollars, render_report
from boss.roles import registry
from boss.roles.builders import PROFILES
from boss.roles.org import org_chart, render_org
from boss.rule import FiringPolicy
from boss.rundir import Recorder, RunPaths
from boss.runner import run_slice
from boss.state import run_state
from boss.stream import Usage
from boss.termsheet import TermSheet, TermSheetError
from boss.worker import CLI, IsolationError, billing_mode, usd, worker_env

RUNS_DIR = Path(".boss") / "runs"
EXECUTABLE_VAR = "BOSS_CLAUDE_BIN"  # override the `claude` binary, e.g. for tests
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_INTERRUPTED = 0, 1, 2, 3, 130

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
    if args.command == "resume":
        return _resume(args, project, environ, ask, say)
    if args.command == "roles":
        say(render_org(org_chart(registry(), PROFILES, FirmConfig().profile)).rstrip("\n"))
        return EXIT_OK
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
        "--rounds", type=_count_arg, default=1, help="funding rounds to split the budget into"
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
    fund.add_argument(
        "--max-tasks", type=_count_arg, default=1, help="most tasks the boss may split into"
    )
    fund.add_argument(
        "--profile",
        choices=[p.name for p in PROFILES],
        help="worker profile: skills added to the builder's prompt (default: none)",
    )
    fund.add_argument(
        "--parallel",
        type=_count_arg,
        default=1,
        help="tasks to work on at once (each task still has one worker at a time)",
    )
    fund.add_argument("--max-slices", type=_count_arg, default=FiringPolicy().max_slices)
    fund.add_argument("--stall-slices", type=_count_arg, default=FiringPolicy().stall_slices)
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
        ("resume", "continue an interrupted, paused or stopped run from its ledger"),
        ("report", "print the board report for a run"),
        ("status", "one-line state of a run"),
    ):
        shown = sub.add_parser(name, parents=[common], help=text)
        shown.add_argument("run", nargs="?", help="run id (default: the latest)")
    sub.add_parser(
        "roles", parents=[common], help="print the organisation: roles, profiles, skills"
    )
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


def _count_arg(text: str) -> int:
    if not text.isdecimal() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of 1 or more")
    return int(text)


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
    if not args.idea.strip() or args.idea.lstrip().startswith("-"):
        say("The idea must be some text, and must not start with '-' (it would read as an option).")
        return EXIT_USAGE
    if args.slice < MIN_SLICE_MICROS:
        say(f"--slice must be at least ${usd(MIN_SLICE_MICROS)}: a smaller slice is never funded.")
        return EXIT_USAGE
    needed = min_round_budget(args.reserve)
    if args.budget // args.rounds < needed:  # refused before anything is spent
        say(
            f"${usd(args.budget)} over {args.rounds} round(s) cannot fund one worker "
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
            parallel=args.parallel,
            profile=args.profile,
            limits=RunLimits(max_seconds=args.max_minutes * 60 if args.max_minutes else None),
        )
        outcome = _run(sheet, paths, ledger, run_id, env, executable, config, ask, say)
    return _finish(paths, outcome, say)


def _run(
    sheet: TermSheet,
    paths: RunPaths,
    ledger: LedgerWriter,
    run_id: str,
    env: Mapping[str, str],
    executable: str,
    config: FirmConfig | None,
    ask: Ask,
    say: Say,
) -> FirmReport | int:
    """Run (or continue) the firm. An exit code instead of a report when it could not finish."""
    cancel = threading.Event()  # set on Ctrl-C, so slices running in other threads stop too
    try:
        return run_firm(
            sheet,
            paths,
            ledger,
            run_id,
            env=env,
            config=config,
            ask=ask,
            say=say,
            slice_runner=functools.partial(run_slice, executable=executable, stop=cancel),
            cancel=cancel,
        )
    except IsolationError as exc:
        say(f"Stopped: the worker did not start isolated ({exc}). Run `boss doctor`.")
    except NotApprovedError as exc:
        say(f"Stopped: {exc}. Nothing was spent.")
    except KeyboardInterrupt:
        say(f"Interrupted. Nothing is lost: continue with `boss resume {run_id}`.")
        return EXIT_INTERRUPTED
    return EXIT_FAILED


def _finish(paths: RunPaths, outcome: FirmReport | int, say: Say) -> int:
    if isinstance(outcome, int):
        return outcome
    text = render_report(build_report(read_events(paths.ledger)))
    (paths.root / "report.md").write_text(text, encoding="utf-8")
    say(text)
    if outcome.stopped:
        say(f"Ended early: {outcome.stopped}")
        if not outcome.all_passed:
            say(f"To continue this run: `boss resume {paths.root.name}`")
    say(f"Run folder: {paths.root}  (built files: {paths.product})")
    return EXIT_OK if outcome.all_passed else EXIT_INCOMPLETE


def _resume(
    args: argparse.Namespace, project: Path, environ: Mapping[str, str], ask: Ask, say: Say
) -> int:
    """Continue a run from its ledger. The investor running this lifts any earlier stop; the
    approval, the budget and every limit are verified again as the run goes on."""
    run = _find_run(args, project, say)
    if run is None:
        return EXIT_FAILED
    try:
        return _resume_run(run, project, environ, ask, say)
    except LedgerLockedError:  # the repair and the writer take the lock before writing anything
        say(
            f"Run {run} is still being written by another `boss` process. Nothing was changed; "
            "let it finish or stop it, then resume."
        )
        return EXIT_FAILED


def _resume_run(run: str, project: Path, environ: Mapping[str, str], ask: Ask, say: Say) -> int:
    paths = RunPaths(project / RUNS_DIR / run)
    torn = repair_torn_tail(paths.ledger)
    if torn is not None:
        say(
            f"The ledger's last line was cut off by a hard stop and has been removed: {torn[:80]!r}"
        )
    try:
        sheet = TermSheet.from_json((paths.root / "term_sheet.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TermSheetError) as exc:
        say(f"Run {run} has no usable term sheet ({exc}); it cannot be resumed.")
        return EXIT_FAILED
    try:
        events = read_events(paths.ledger)
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be resumed: its ledger is damaged ({exc}).")
        return EXIT_FAILED
    if started_config(events) is None:
        say(f"Run {run} never got as far as hiring; start again with `boss fund`.")
        return EXIT_FAILED
    env, executable = worker_env(environ), environ.get(EXECUTABLE_VAR, CLI)
    with LedgerWriter(paths.ledger) as ledger:
        stops = [e for e in events if e.event is EventType.STOPPED]
        if run_state(events, [t.id for t in sheet.tasks]).stopped:
            say(f"Run {run} was stopped: {stops[-1].data.get('reason', 'no reason recorded')}")
            Recorder(ledger, run, events[-1].round)("investor", EventType.RESUMED)
        say(f"Resuming run {run}...")
        outcome = _run(sheet, paths, ledger, run, env, executable, None, ask, say)
    return _finish(paths, outcome, say)


def _find_run(args: argparse.Namespace, project: Path, say: Say) -> str | None:
    runs = project / RUNS_DIR
    names = sorted(p.name for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    run = args.run or (names[-1] if names else None)
    if run is None or run not in names:
        say(
            f"No run {run!r} under {runs}."
            if run
            else f"No runs under {runs}. Start one with `boss fund`."
        )
        return None
    return str(run)


def _show(args: argparse.Namespace, project: Path, say: Say) -> int:
    run = _find_run(args, project, say)
    if run is None:
        return EXIT_FAILED
    try:
        events = read_events(RunPaths(project / RUNS_DIR / run).ledger)
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be read: its ledger is damaged ({exc}).")
        return EXIT_FAILED
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
