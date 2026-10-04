"""Command line: `boss fund`, `resume`, `topup`, `report`, `status`, `roles` and `doctor`.

Exit codes:
  0    every required check passes on the product (or the command succeeded)
  1    nothing was built: no usable term sheet, the investor rejected it, a worker did not start
       isolated, the approved checks changed, or the run cannot be read
  2    usage error: a bad option, a blank idea, a budget too small to fund one slice, or roles
       that cannot run together
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
from boss import dispatch as dispatching
from boss.approval import NotApprovedError, review_term_sheet
from boss.boss import DEFAULT_MODEL, BossError, InvalidDraftError, draft_term_sheet
from boss.budget import (
    MIN_SLICE_MICROS,
    min_round_budget,
    plan_rounds,
    remaining,
    reserve_for,
    round_budget,
)
from boss.context import derive_reads, verify
from boss.firm import (
    DEFAULT_SLICE_MICROS,
    DEFAULT_WORKER_MODEL,
    Advise,
    FirmConfig,
    FirmReport,
    run_firm,
    started_config,
)
from boss.held_out import MAX_HELD_OUT
from boss.ledger import (
    Event,
    EventType,
    LedgerCorruptError,
    LedgerLockedError,
    LedgerUnverifiedError,
    LedgerWriter,
    repair_torn_tail,
)
from boss.limits import RunLimits
from boss.pipeline import (
    Pipeline,
    RolesError,
    Setup,
    default_fix_budget,
    parse_roles,
    recorded_setup,
)
from boss.report import build_report, dollars, render_report
from boss.roles import registry
from boss.roles.builders import PROFILES
from boss.roles.org import org_chart, render_org
from boss.rule import FiringPolicy
from boss.rundir import Recorder, RunPaths
from boss.runner import run_slice
from boss.signing import SigningError
from boss.state import run_state
from boss.stream import Usage
from boss.termsheet import TermSheet, TermSheetError
from boss.worker import CLI, IsolationError, ModelMismatchError, billing_mode, usd, worker_env

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
    try:
        if args.command == "fund":
            return _fund(args, project, environ, ask, say)
        if args.command == "resume":
            return _resume(args, project, environ, ask, say)
        if args.command == "topup":
            return _topup(args, project, say)
    except (LedgerUnverifiedError, SigningError) as exc:  # a ledger the key does not vouch for
        say(f"Stopped: {exc}")
        return EXIT_FAILED
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
        help="dollars held back from every slice cap: what one response of the worker model costs "
        "(default: by model, $0.10 for haiku, $0.30 for sonnet, $0.50 for opus)",
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
    fund.add_argument(
        "--held-out",
        type=_held_out_arg,
        default=0,
        help=f"checks an examiner writes that the workers never see, run on the finished product "
        f"(0 to {MAX_HELD_OUT}; default 0, off)",
    )
    fund.add_argument(
        "--dispatch",
        choices=("off", "rules"),
        default="off",
        help="per-task dispatch: 'rules' puts each task's model, effort and route in the term "
        "sheet for you to read and edit, steps a worker up one tier only when the gate fired its "
        "predecessor, and records the model that ran (default: off, every worker on --model)",
    )
    fund.add_argument(
        "--max-tier",
        choices=dispatching.TIERS,
        help="the dearest model dispatch may use; needs --dispatch rules "
        f"(default with it: {dispatching.DEFAULT_MAX_TIER})",
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
    fund.add_argument(
        "--worker-thinking",
        type=_tokens_arg,
        help="thinking tokens per worker slice; 0 turns thinking off (default: the CLI's)",
    )
    fund.add_argument(
        "--roles",
        default="",
        help="specialist roles to run, comma separated, or 'all' (default: none); see `boss roles`",
    )
    _review_options(fund)

    for name, text in (
        ("resume", "continue an interrupted, paused or stopped run from its ledger"),
        ("report", "print the board report for a run"),
        ("status", "one-line state of a run"),
    ):
        shown = sub.add_parser(name, parents=[common], help=text)
        shown.add_argument("run", nargs="?", help="run id (default: the latest)")
        if name == "resume":
            _review_options(shown)
    topup = sub.add_parser(
        "topup", parents=[common], help="add money to a round of a run; reopens a locked round"
    )
    topup.add_argument("run", nargs="?", help="run id (default: the latest)")
    topup.add_argument("--round", required=True, type=_count_arg, help="round to add money to")
    topup.add_argument("--amount", required=True, type=usd_arg, help="dollars to add, e.g. 0.20")
    sub.add_parser(
        "roles", parents=[common], help="print the organisation: roles, profiles, skills"
    )
    doctor = sub.add_parser("doctor", parents=[common], help="check that this machine can run boss")
    doctor.add_argument("--live", action="store_true", help="verify login with one small real call")
    return parser


def _review_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--review-cycles",
        type=_cycles_arg,
        default=1,
        help="times the critic may review the product and offer a fix round; 0 reports findings "
        "and offers nothing (default: 1)",
    )
    parser.add_argument(
        "--fix-budget",
        type=usd_arg,
        help="dollars for a fix round after the critic's findings (default: two slices and one "
        "reserve)",
    )


def usd_arg(text: str) -> int:
    try:
        micros = Decimal(text.lstrip("$")) * 1_000_000
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"{text!r} is not a dollar amount") from None
    if micros <= 0 or micros != micros.to_integral_value():
        raise argparse.ArgumentTypeError(
            f"{text!r} is not a positive dollar amount with at most 6 decimal places"
        )
    return int(micros)


def _held_out_arg(text: str) -> int:
    if not text.isdecimal() or int(text) > MAX_HELD_OUT:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number from 0 to {MAX_HELD_OUT}")
    return int(text)


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


def _cycles_arg(text: str) -> int:
    if not text.isdecimal():
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number of 0 or more")
    return int(text)


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
    refusal = _dispatch_refusal(args)
    if refusal is not None:
        say(refusal)
        return EXIT_USAGE
    reserve = args.reserve if args.reserve is not None else reserve_for(args.model)
    needed = min_round_budget(reserve)
    # Rounds are capped at the number of checks, which the boss has not drafted yet: only the best
    # case (one round) can be judged here. The real round plan is checked after the draft.
    if args.budget < needed:  # refused before anything is spent
        say(
            f"${usd(args.budget)} cannot fund one worker slice: a round needs at least "
            f"${usd(needed)} (${usd(reserve)} reserve plus a ${usd(MIN_SLICE_MICROS)} slice). "
            "Raise --budget or lower --reserve."
        )
        return EXIT_USAGE
    try:
        roles = parse_roles(args.roles, registry())
    except RolesError as exc:
        say(str(exc))
        return EXIT_USAGE
    if args.fix_budget is not None and args.fix_budget < needed:
        say(_fix_budget_refusal(needed, reserve))
        return EXIT_USAGE
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    paths = RunPaths(project / RUNS_DIR / run_id)
    paths.root.mkdir(parents=True)
    say(f"Run {run_id}: drafting the term sheet...")
    with paths.writer() as ledger:
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

        def draft_boss() -> TermSheet | None:
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
                return None
            boss_spend(draft.usage, "completed")
            if args.rounds > 1:
                rounds = plan_rounds(
                    args.budget, len(draft.sheet.checks), args.rounds, min_round_micros=needed
                )
                return dataclasses.replace(draft.sheet, rounds=rounds)
            return draft.sheet

        policy = _dispatch_policy(args)
        pipe = Pipeline(
            Setup(roles, args.boss_model, args.boss_thinking),
            project, paths, ledger, run_id, env, executable, ask, say, policy,
        )  # fmt: skip
        try:
            plan = pipe.plan(
                args.idea,
                args.budget,
                max_tasks=args.max_tasks,
                n_rounds=args.rounds,
                reserve_micros=reserve,
                draft_boss=draft_boss,
            )
        except KeyboardInterrupt:  # no term sheet is approved yet, so there is nothing to resume
            record("investor", EventType.STOPPED, data={"reason": "interrupted before approval"})
            say(
                "Interrupted before the term sheet was approved. Nothing was funded; what the "
                f"calls so far cost is on the ledger ({paths.ledger}). "
                "Start again with `boss fund`."
            )
            return EXIT_INTERRUPTED
        if plan is None:
            return EXIT_FAILED
        thinnest = min(r.budget_micros for r in plan.sheet.rounds)
        if thinnest < needed:  # the draft is paid for, but nothing is funded: no worker is hired
            reason = (
                f"the plan has {len(plan.sheet.rounds)} round(s) and the smallest has "
                f"${usd(thinnest)}, but a round needs at least ${usd(needed)}"
            )
            record("boss", EventType.STOPPED, data={"reason": reason})
            say(f"Stopped before approval: {reason}. Raise --budget, lower --rounds or --reserve.")
            return EXIT_FAILED
        view = None
        if policy is not None:
            planned = dispatching.plan_dispatch(
                plan.sheet,
                tier=dispatching.tier_of(args.model) or args.model,
                profile=args.profile,
                policy=policy,
                reads=derive_reads(plan.sheet, paths.checks),
            )
            if refused := dispatching.dispatch_problems(planned, policy):
                reason = "the dispatch cannot run: " + "; ".join(refused)
                record("boss", EventType.STOPPED, data={"reason": reason})
                say(f"Stopped before approval: {reason}. Raise --budget or lower --model.")
                return EXIT_FAILED
            plan = dataclasses.replace(plan, sheet=planned)
            level = dispatching.RunLevel(
                args.boss_model,
                "critic" if "critic" in roles else "off",
                args.held_out,
                args.parallel,
            )
            view = dispatching.DispatchView(policy, level, args.stall_slices, {})
        held = args.held_out > 0 and pipe.examine(plan.sheet, args.held_out, reserve)
        try:
            sheet = review_term_sheet(
                plan.sheet,
                paths.checks,
                paths.root,
                ledger,
                run_id,
                ask=ask,
                say=say,
                notes=plan.notes,
                held_out_dir=paths.held_out if held else None,
                view=view,
            )
        except SigningError as exc:
            say(f"The approval could not be signed, so nothing was funded: {exc}")
            return EXIT_FAILED
        if sheet is None:
            return EXIT_FAILED
        say("Approved. Hiring a worker...")
        config = FirmConfig(
            model=args.model,
            slice_micros=args.slice,
            reserve_micros=reserve,
            policy=FiringPolicy(stall_slices=args.stall_slices, max_slices=args.max_slices),
            firing=not args.no_firing,
            parallel=args.parallel,
            profile=args.profile,
            limits=RunLimits(max_seconds=args.max_minutes * 60 if args.max_minutes else None),
            held_out=args.held_out,
            thinking_tokens=args.worker_thinking,
            dispatch=policy is not None,
            max_tier=policy.max_tier if policy is not None else dispatching.DEFAULT_MAX_TIER,
        )
        pipe.record_start(config)
        fix = args.fix_budget or default_fix_budget(config)
        outcome = _build(pipe, sheet, config, args.review_cycles, fix)
    return _finish(paths, outcome, say)


def _dispatch_refusal(args: argparse.Namespace) -> str | None:
    """Why the dispatch flags cannot be used together, before anything is spent."""
    if args.dispatch == "off":
        return "--max-tier needs --dispatch rules." if args.max_tier else None
    tier = dispatching.tier_of(args.model)
    if tier is None:
        return f"--dispatch rules needs --model to be one of {', '.join(dispatching.TIERS)}."
    top = args.max_tier or dispatching.DEFAULT_MAX_TIER
    if dispatching.rank(tier) > dispatching.rank(top):
        return f"--model {tier} is above --max-tier {top}; raise --max-tier."
    if args.reserve is not None:
        return "--reserve cannot be used with --dispatch rules: the reserve is per model."
    return None


def _dispatch_policy(args: argparse.Namespace) -> dispatching.DispatchPolicy | None:
    if args.dispatch == "off":
        return None
    return dispatching.DispatchPolicy(args.max_tier or dispatching.DEFAULT_MAX_TIER, args.slice)


def _fix_budget_refusal(needed: int, reserve: int) -> str:
    return (
        f"--fix-budget must be at least ${usd(needed)}: a round needs the ${usd(reserve)} "
        f"reserve plus a ${usd(MIN_SLICE_MICROS)} slice."
    )


def _build(
    pipe: Pipeline, sheet: TermSheet, config: FirmConfig | None, cycles: int, fix_micros: int
) -> FirmReport | int:
    """Run the firm, then whatever the chosen roles do with what it built. The fix round the
    critic may lead to is the same loop on an amended sheet."""

    def run(current: TermSheet) -> FirmReport | int:
        return _run(
            current,
            pipe.paths,
            pipe.ledger,
            pipe.run_id,
            pipe.env,
            pipe.executable,
            config,
            pipe.ask,
            pipe.say,
            pipe.advisor(current),
        )

    outcome = run(sheet)
    if isinstance(outcome, int):
        return outcome
    try:
        return pipe.after_build(sheet, outcome, run, review_cycles=cycles, fix_micros=fix_micros)
    except KeyboardInterrupt:
        pipe.say(f"Interrupted. Nothing is lost: continue with `boss resume {pipe.run_id}`.")
        return EXIT_INTERRUPTED


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
    advise: Advise | None = None,
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
            advise=advise,
        )
    except IsolationError as exc:
        say(f"Stopped: the worker did not start isolated ({exc}). Run `boss doctor`.")
    except ModelMismatchError as exc:
        say(f"Stopped: the wrong model ran ({exc}). The slice was booked; nothing more was spent.")
    except NotApprovedError as exc:
        say(f"Stopped: {exc}. Nothing was spent.")
    except KeyboardInterrupt:
        say(f"Interrupted. Nothing is lost: continue with `boss resume {run_id}`.")
        return EXIT_INTERRUPTED
    return EXIT_FAILED


def _finish(paths: RunPaths, outcome: FirmReport | int, say: Say) -> int:
    if isinstance(outcome, int):
        return outcome
    events = paths.events()
    text, unverified = _report_text(paths, events)
    (paths.root / "report.md").write_text(text, encoding="utf-8")
    say(text)
    if outcome.stopped:
        say(f"Ended early: {outcome.stopped}")
        if not outcome.all_passed:
            say(f"To continue this run: `boss resume {paths.root.name}`")
    say(f"Run folder: {paths.root}  (built files: {paths.product})")
    if unverified:
        return EXIT_FAILED
    return EXIT_OK if outcome.all_passed else EXIT_INCOMPLETE


def _report_text(paths: RunPaths, events: Sequence[Event]) -> tuple[str, list[str]]:
    """The board report, with a failure line for each saved prompt that no longer matches the
    hash its slice recorded (only a run with dispatch on has any to check)."""
    text = render_report(build_report(events))
    problems = verify(paths, events)
    if problems:
        text += "\nCONTEXT CHECK FAILED: what a worker was given is not what was recorded\n"
        text += "".join(f"  {p}\n" for p in problems)
    return text, problems


def _resume(
    args: argparse.Namespace, project: Path, environ: Mapping[str, str], ask: Ask, say: Say
) -> int:
    """Continue a run from its ledger. The investor running this lifts any earlier stop; the
    approval, the budget and every limit are verified again as the run goes on."""
    run = _find_run(args, project, say)
    if run is None:
        return EXIT_FAILED
    try:
        return _resume_run(args, run, project, environ, ask, say)
    except LedgerLockedError:  # the repair and the writer take the lock before writing anything
        say(_held_by_another(run, "resume"))
        return EXIT_FAILED


def _held_by_another(run: str, then: str) -> str:
    return (
        f"Run {run} is still being written by another `boss` process. Nothing was changed; "
        f"let it finish or stop it, then {then}."
    )


def _resume_run(
    args: argparse.Namespace,
    run: str,
    project: Path,
    environ: Mapping[str, str],
    ask: Ask,
    say: Say,
) -> int:
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
        events = paths.events()
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be resumed: its ledger is damaged ({exc}).")
        return EXIT_FAILED
    config = started_config(events)
    if config is None:
        say(f"Run {run} never got as far as hiring; start again with `boss fund`.")
        return EXIT_FAILED
    needed = min_round_budget(config.reserve_micros)
    if args.fix_budget is not None and args.fix_budget < needed:
        say(_fix_budget_refusal(needed, config.reserve_micros))
        return EXIT_USAGE
    env, executable = worker_env(environ), environ.get(EXECUTABLE_VAR, CLI)
    # The roles a run was started with are on its ledger; a run without any resumes without any.
    setup = recorded_setup(events) or Setup((), DEFAULT_MODEL, None)
    with paths.writer() as ledger:
        policy = config.dispatch_policy()
        pipe = Pipeline(setup, project, paths, ledger, run, env, executable, ask, say, policy)
        stops = [e for e in events if e.event is EventType.STOPPED]
        if run_state(events, [t.id for t in sheet.tasks]).stopped:
            say(f"Run {run} was stopped: {stops[-1].data.get('reason', 'no reason recorded')}")
            Recorder(ledger, run, events[-1].round)("investor", EventType.RESUMED)
        say(f"Resuming run {run}...")
        fix = args.fix_budget or default_fix_budget(config)
        outcome = _build(pipe, sheet, None, args.review_cycles, fix)
    return _finish(paths, outcome, say)


def _topup(args: argparse.Namespace, project: Path, say: Say) -> int:
    """Record the investor's top-up of one round. The loop, not this command, spends it."""
    run = _find_run(args, project, say)
    if run is None:
        return EXIT_FAILED
    paths = RunPaths(project / RUNS_DIR / run)
    try:
        # Repaired before the writer opens: appending after a cut line would bury it mid-file.
        torn = repair_torn_tail(paths.ledger)
        if torn is not None:
            say(f"The ledger's last line was cut off and has been removed: {torn[:80]!r}")
        sheet = TermSheet.from_json((paths.root / "term_sheet.json").read_text(encoding="utf-8"))
        with paths.writer() as ledger:  # held from the checks to the write
            events = paths.events()
            refusal = _topup_refusal(sheet, events, args.round, run)
            if refusal is not None:
                say(refusal)
                return EXIT_USAGE
            Recorder(ledger, run, args.round)(
                "investor", EventType.TOPPED_UP, data={"micros": args.amount}
            )
            events = paths.events()
    except LedgerLockedError:
        say(_held_by_another(run, "top up"))
        return EXIT_FAILED
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be topped up: its ledger is damaged ({exc}).")
        return EXIT_FAILED
    except (OSError, ValueError, TermSheetError) as exc:
        say(f"Run {run} cannot be topped up: {exc}")
        return EXIT_FAILED
    left = remaining(sheet, events, args.round)
    say(
        f"Topped up round {args.round} of run {run} by ${usd(args.amount)}: its budget is now "
        f"${usd(round_budget(sheet, events, args.round))}, ${usd(max(left, 0))} left."
    )
    config = started_config(events)
    needed = min_round_budget(config.reserve_micros) if config is not None else 0
    if left < needed:
        say(f"That cannot fund a slice yet: a round needs ${usd(needed)} left (reserve + slice).")
    say(f"Continue with `boss resume {run}`.")
    return EXIT_OK


def _topup_refusal(sheet: TermSheet, events: Sequence[Event], round_n: int, run: str) -> str | None:
    if round_n not in {r.n for r in sheet.rounds}:
        rounds = ", ".join(str(r.n) for r in sheet.rounds)
        return f"Run {run} has no round {round_n}; its rounds are {rounds}."
    state = run_state(events, [t.id for t in sheet.tasks])
    if round_n in state.closed_rounds and round_n not in state.locked_rounds:
        return (
            f"Round {round_n} of run {run} closed with its checks unlocked: money added there "
            "would never be spent. Top up a round that is open or locked."
        )
    return None


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
        events = RunPaths(project / RUNS_DIR / run).events()
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be read: its ledger is damaged ({exc}).")
        return EXIT_FAILED
    if not events:
        say(f"Run {run} has an empty ledger.")
        return EXIT_FAILED
    report = build_report(events)
    if args.command == "report":
        text, unverified = _report_text(RunPaths(project / RUNS_DIR / run), events)
        say(text)
        return EXIT_FAILED if unverified else EXIT_OK
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
