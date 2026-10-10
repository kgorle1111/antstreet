"""Commands: `fund`, `approve`, `resume`, `topup`, `report`, `status`, `routing`, `verify`, `roles`,
`doctor`, `mcp`, `audit`.

Exit codes:
  0    every required check passes on the product (or the command succeeded)
  1    nothing was built: no usable term sheet, the investor rejected it, a worker did not start
       isolated or ran the wrong model, the approved checks changed, or the run cannot be read
  2    usage error: a bad option, a blank idea, a budget too small to fund one slice, roles that
       cannot run together, or (for `verify`) no such run
  3    the run ended with a check still failing, for any reason (out of budget, a limit, a pause,
       a declined round, a task set aside); for `antstreet audit check`, a refuted or inconclusive
       verdict
  4    no terminal to ask on: the drafted term sheet (`fund`) or a worker's dispute of a check
       (`fund`, `resume`) waits for `antstreet approve`
  130  interrupted; continue with `antstreet resume`
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import json
import os
import sys
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from antstreet import (
    __version__,
    audit,
    audit_check,
    audit_report,
    held_out,
    mutate,
    routing,
    rulings,
    spec,
)
from antstreet import dispatch as dispatching
from antstreet.approval import (
    TERM_SHEET_FILE,
    NotApprovedError,
    SpecView,
    approve_shown,
    pending,
    review_term_sheet,
    shown_digest,
    spec_view,
)
from antstreet.boss import (
    DEFAULT_MODEL,
    RULES_PROMPT,
    BossError,
    InvalidDraftError,
    draft_term_sheet,
)
from antstreet.budget import (
    MIN_SLICE_MICROS,
    min_round_budget,
    plan_rounds,
    remaining,
    reserve_for,
    round_budget,
)
from antstreet.context import derive_reads, verify
from antstreet.errors import Outcome
from antstreet.firm import (
    DEFAULT_SLICE_MICROS,
    DEFAULT_WORKER_MODEL,
    Advise,
    FirmConfig,
    FirmReport,
    config_data,
    run_firm,
    started_config,
)
from antstreet.gate import GateError
from antstreet.gitrepo import GitError
from antstreet.held_out import MAX_HELD_OUT
from antstreet.ledger import (
    Event,
    EventType,
    LedgerCorruptError,
    LedgerLockedError,
    LedgerUnverifiedError,
    LedgerWriter,
    adopt_unsigned,
    repair_torn_tail,
    unsigned_lines,
)
from antstreet.limits import RunLimits
from antstreet.pipeline import (
    Pipeline,
    Plan,
    RolesError,
    Setup,
    default_fix_budget,
    parse_roles,
    recorded_setup,
)
from antstreet.report import build_report, dollars, render_report
from antstreet.roles import registry
from antstreet.roles.builders import PROFILES
from antstreet.roles.org import org_chart, render_org
from antstreet.rule import FiringPolicy
from antstreet.rundir import Recorder, RunPaths
from antstreet.runner import run_slice
from antstreet.signing import SigningError
from antstreet.state import run_state
from antstreet.stream import Usage
from antstreet.termsheet import TermSheet, TermSheetError
from antstreet.worker import (
    CLI,
    EXECUTABLE_VAR,
    IsolationError,
    ModelMismatchError,
    billing_mode,
    usd,
    worker_env,
)

RUNS_DIR = Path(".boss") / "runs"
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_INCOMPLETE, EXIT_INTERRUPTED = 0, 1, 2, 3, 130
EXIT_AWAITING = 4
AWAITING = "awaiting the investor's approval"  # the `stopped` reason of a deferred approval
LOGIN_FIX = (
    "The Claude CLI that AntStreet starts is not logged in: its login expired or could not be "
    "refreshed (with ANTHROPIC_API_KEY set, the key was refused). Run `claude auth login` in a "
    "terminal, check with `antstreet doctor --live`, then run again."
)

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
    if args.command == "audit":
        return _audit(args, environ, ask, say)
    project = Path(args.dir).resolve()
    try:
        if args.command == "fund":
            return _fund(args, project, environ, ask, say)
        if args.command == "resume":
            return _resume(args, project, environ, ask, say)
        if args.command == "approve":
            return _approve(args, project, say)
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
    if args.command == "routing":
        say("\n".join(routing.render_routing(routing.read_runs(project), top=args.max_tier)))
        return EXIT_OK
    if args.command == "verify":
        return _verify(args, project, say)
    if args.command == "mcp":
        from antstreet.mcp import serve

        return serve(project, sys.stdin, sys.stdout, environ)
    return _show(args, project, say)


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dir", default=".", help="project folder (default: current)")
    parser = argparse.ArgumentParser(
        prog="antstreet",
        description=(
            "Check an AI coding agent's work against sealed tests it never saw (audit), "
            "or fund a budget-capped build (experimental)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"antstreet {__version__}")
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
        choices=("off", "rules", "cascade"),
        default="off",
        help="per-task dispatch: 'rules' puts each task's model, effort and route in the term "
        "sheet for you to read and edit, steps a worker up one tier only when the gate fired its "
        "predecessor, and records the model that ran; 'cascade' starts each task on the tier "
        "its past runs say is cheapest and climbs haiku > sonnet > opus > opus at more effort, "
        "one rung per verified failure, then asks you (default: off, every worker on --model)",
    )
    fund.add_argument(
        "--max-tier",
        choices=dispatching.TIERS,
        help="the dearest model dispatch may use; needs --dispatch rules or cascade "
        f"(default with it: {dispatching.DEFAULT_MAX_TIER})",
    )
    fund.add_argument(
        "--spec",
        action="store_true",
        help="the boss's checks must cite the rules of your idea (its own sentences, numbered by "
        "code) and you see which rules no check covers before you approve; one task (default: off)",
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
        help="specialist roles to run, comma separated, or 'all' (default: none; critic is the "
        "one to try); see `antstreet roles`",
    )
    _review_options(fund)

    for name, text in (
        ("resume", "continue an interrupted, paused or stopped run from its ledger"),
        ("report", "print the board report for a run"),
        ("status", "one-line state of a run"),
        ("verify", "check a run's ledger, signatures and saved prompts; no model call"),
    ):
        shown = sub.add_parser(name, parents=[common], help=text)
        shown.add_argument("run", nargs="?", help="run id (default: the latest)")
        if name == "resume":
            _review_options(shown)
        if name == "status":
            shown.add_argument(
                "--json", action="store_true", help="one JSON object, for tools (Claude Code mod)"
            )
        if name == "verify":
            shown.add_argument(
                "--adopt-unsigned",
                action="store_true",
                help="vouch for a run with unsigned lines and no anchor as it is now",
            )
    approve = sub.add_parser(
        "approve",
        parents=[common],
        help="show a term sheet `fund` left waiting, or approve exactly the one shown",
    )
    approve.add_argument("run", nargs="?", help="run id (default: the latest)")
    approve.add_argument(
        "--sheet", help="the value printed with the term sheet you read: approves that text only"
    )
    approve.add_argument(
        "--dispute", metavar="CHECK", help="rule on the dispute of CHECK the run is waiting on"
    )
    approve.add_argument(
        "--ruling",
        choices=("drop", "keep"),
        help="with --dispute: drop the check, or keep it (the worker must satisfy it)",
    )
    topup = sub.add_parser(
        "topup", parents=[common], help="add money to a round of a run; reopens a locked round"
    )
    topup.add_argument("run", nargs="?", help="run id (default: the latest)")
    topup.add_argument("--round", required=True, type=_count_arg, help="round to add money to")
    topup.add_argument("--amount", required=True, type=usd_arg, help="dollars to add, e.g. 0.20")
    routed = sub.add_parser(
        "routing",
        parents=[common],
        help="print the start tier the cascade would choose per task kind, from past runs",
    )
    routed.add_argument(
        "--max-tier",
        choices=dispatching.TIERS,
        default=dispatching.DEFAULT_MAX_TIER,
        help=f"the top of the ladder to price (default: {dispatching.DEFAULT_MAX_TIER})",
    )
    sub.add_parser(
        "roles", parents=[common], help="print the organisation: roles, profiles, skills"
    )
    doctor = sub.add_parser(
        "doctor", parents=[common], help="check that this machine can run antstreet"
    )
    doctor.add_argument("--live", action="store_true", help="verify login with one small real call")
    sub.add_parser(
        "mcp",
        parents=[common],
        help="serve this project's runs read-only to an MCP client on stdin/stdout",
    )
    _audit_parser(sub)
    return parser


def _audit_parser(sub: Any) -> None:
    audit_cmd = sub.add_parser(
        "audit",
        help="check someone else's change against checks sealed before it, from a repo's git",
        description="Seal checks for a change request, then run them on a commit an agent made.",
    )
    steps = audit_cmd.add_subparsers(dest="audit_command", required=True)
    plan = steps.add_parser(
        "plan", help="write and seal checks for a request, from a base commit alone"
    )
    plan.add_argument(
        "--repo", default=".", help="the git checkout to audit, not modified (default: .)"
    )
    plan.add_argument("--request", required=True, help="a text file holding the change request")
    plan.add_argument(
        "--base",
        default="HEAD",
        help="the branch, tag or commit before the change (default: HEAD, as it is before the "
        "agent starts)",
    )
    plan.add_argument(
        "--held-out",
        type=_held_out_arg,
        default=0,
        help=f"checks an examiner writes as well, from the request alone (0 to {MAX_HELD_OUT}; "
        "default 0, off)",
    )
    plan.add_argument("--boss-model", default=DEFAULT_MODEL, help="model for the boss's own calls")
    check = steps.add_parser(
        "check", help="run a run's sealed checks on a commit and record the gate's verdict"
    )
    check.add_argument(
        "run", nargs="?", help="the run id `antstreet audit plan` printed (default: the latest)"
    )
    check.add_argument(
        "--head", default="HEAD", help="the branch, tag or commit to audit (default: HEAD)"
    )
    check.add_argument("--repo", default=".", help="the git checkout holding the head (default: .)")
    check.add_argument(
        "--claim",
        choices=audit_check.CLAIMS,
        default="none",
        help="what the agent said of its own work: done, or none (default: none)",
    )
    check.add_argument(
        "--claim-text", help="a file with the agent's own words; kept as a hash only"
    )
    check.add_argument("--agent", type=_agent_arg, help="a label for the agent, to report by")
    check.add_argument(
        "--no-strength",
        action="store_true",
        help="skip measuring how many mutants of the change each counted check kills",
    )
    check.add_argument(
        "--max-mutants",
        type=_mutants_arg,
        default=mutate.DEFAULT_CAP,
        help=f"most mutants for the check strength (1 to {MAX_MUTANTS}; default "
        f"{mutate.DEFAULT_CAP})",
    )
    check.add_argument(
        "--strength-timeout",
        type=_seconds_arg,
        default=audit_check.STRENGTH_TIMEOUT_S,
        help="seconds for every mutant together; no new mutant starts after it (default "
        f"{audit_check.STRENGTH_TIMEOUT_S:g})",
    )
    report = steps.add_parser("report", help="verdicts per run, and the false-pass rate")
    report.add_argument("run", nargs="?", help="audit run id (default: the latest)")
    report.add_argument("--all", action="store_true", help="every run in the store")
    report.add_argument("--agent", type=_agent_arg, help="only this agent's verdicts")


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


def _agent_arg(text: str) -> str:
    try:
        return audit_check.agent_label(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


MAX_MUTANTS = 500


def _mutants_arg(text: str) -> int:
    if not text.isdecimal() or not 1 <= int(text) <= MAX_MUTANTS:
        raise argparse.ArgumentTypeError(f"{text!r} is not a whole number from 1 to {MAX_MUTANTS}")
    return int(text)


def _seconds_arg(text: str) -> float:
    try:
        seconds = float(text)
    except ValueError:
        seconds = -1.0
    if not 0 < seconds <= 86_400:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds from 0 to 86400")
    return seconds


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
    rules: spec.Split | None = None
    if args.spec:
        refusal = _spec_refusal(args, roles)
        if refusal:
            say(refusal)
            return EXIT_USAGE
        try:
            rules = spec.split(args.idea.strip())
        except spec.SpecError as exc:
            say(f"--spec cannot cover this idea rule by rule: {exc}")
            return EXIT_USAGE
        if not rules.scorable:
            say(
                "--spec found no rule in the idea to cover: it has no sentence stating a behaviour."
            )
            return EXIT_USAGE
    run_id = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    paths = RunPaths(project / RUNS_DIR / run_id)
    paths.root.mkdir(parents=True)
    if rules is not None:
        paths.rules.write_text(spec.dumps(rules), encoding="utf-8")
    waivers: dict[str, str] = {}  # rules the boss left untested, with its reasons
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
                    **({"prompt": RULES_PROMPT, "rules": len(rules.scorable)} if rules else {}),
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
                    rules=rules,
                )
            except BossError as exc:
                boss_spend(exc.usage, str(exc.outcome))
                record("boss", EventType.STOPPED, data={"reason": str(exc)})
                say(f"The boss could not produce a term sheet: {exc}")
                if exc.outcome is Outcome.LOGIN:
                    say(LOGIN_FIX)
                if isinstance(exc, InvalidDraftError):
                    say("\n".join(f"  - {p}" for p in exc.problems))
                return None
            boss_spend(draft.usage, "completed")
            waivers.update(draft.untested)
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
                "Start again with `antstreet fund`."
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
        chosen: dict[str, routing.Choice] = {}
        if policy is not None:
            reads = derive_reads(plan.sheet, paths.checks)
            if policy.cascade:
                chosen = routing.starts_for(
                    plan.sheet,
                    routing.read_runs(project).stats,
                    top=policy.max_tier,
                    fundable=lambda t: dispatching.fits(t, thinnest, policy.slice_micros),
                )
                planned = dispatching.plan_cascade(
                    plan.sheet,
                    starts={k: c.tier for k, c in chosen.items()},
                    profile=args.profile,
                    policy=policy,
                    reads=reads,
                )
            else:
                planned = dispatching.plan_dispatch(
                    plan.sheet,
                    tier=dispatching.tier_of(args.model) or args.model,
                    profile=args.profile,
                    policy=policy,
                    reads=reads,
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
            shown = {k: c.record(policy.max_tier) for k, c in chosen.items()}
            view = dispatching.DispatchView(policy, level, args.stall_slices, {}, shown)
        held = args.held_out > 0 and pipe.examine(plan.sheet, args.held_out, reserve)
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
            cascade=policy is not None and policy.cascade,
        )
        spec_shown = spec_view(paths.rules, paths.checks, waivers) if rules else None
        if _unattended(ask):  # EOF would reject the draft
            return _await_approval(pipe, plan, config, view, spec_shown, waivers)
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
                spec_shown=spec_shown,
                rules_path=paths.rules if rules else None,
            )
        except SigningError as exc:
            say(f"The approval could not be signed, so nothing was funded: {exc}")
            return EXIT_FAILED
        if sheet is None:
            return EXIT_FAILED
        say("Approved. Hiring a worker...")
        pipe.record_start(config)
        fix = args.fix_budget or default_fix_budget(config)
        outcome = _build(pipe, sheet, config, args.review_cycles, fix)
    return _finish(paths, outcome, say)


def _unattended(ask: Ask) -> bool:
    """Nobody is at a terminal to answer: the real `input` on a stdin that is not a TTY."""
    return ask is input and not (sys.stdin and sys.stdin.isatty())


def _await_approval(
    pipe: Pipeline,
    plan: Plan,
    config: FirmConfig,
    view: dispatching.DispatchView | None,
    spec_shown: SpecView | None,
    waivers: Mapping[str, str],
) -> int:
    """`fund` with nobody at a terminal to answer: keep the paid-for draft, unapproved, and wait
    for `antstreet approve`, where end of input would have read as a rejection. The configuration
    goes
    on `started` now, so `antstreet resume` builds exactly what was asked for once it is
    approved."""
    paths, run = pipe.paths, pipe.run_id
    sheet = dataclasses.replace(plan.sheet, approved_by_investor=False)
    (paths.root / TERM_SHEET_FILE).write_text(sheet.to_json())
    record = Recorder(pipe.ledger, run, 0)
    started = {"config": config_data(config), "roles": pipe.setup.data()}
    record("boss", EventType.STARTED, data=started)
    data = {"reason": AWAITING, "untested": dict(waivers), "notes": list(plan.notes)}
    record("boss", EventType.STOPPED, data=data)
    _show_pending(paths, run, view, spec_shown, plan.notes, pipe.say)
    pipe.say("Nothing was funded; only the draft was paid for. Do not run `antstreet fund` again.")
    return EXIT_AWAITING


def _show_pending(
    paths: RunPaths,
    run: str,
    view: dispatching.DispatchView | None,
    spec_shown: SpecView | None,
    notes: Sequence[str],
    say: Say,
) -> bool:
    """Print the waiting term sheet and the one command that approves exactly that text."""
    held_dir = paths.held_out if held_out.hashes(paths.held_out) else None
    try:
        _, _, text = pending(paths.root / TERM_SHEET_FILE, paths.checks, held_dir, view, spec_shown)
    except (TermSheetError, spec.SpecError) as exc:
        say(f"Run {run}: the term sheet cannot be approved as it stands: {exc}")
        return False
    say(text)
    for note in notes:
        say(note)
    say(
        f"\nRun {run} is {AWAITING}. Read the term sheet and every check above; to approve "
        f"exactly that, run this yourself:\n  antstreet approve {run} --sheet "
        f"{shown_digest(text)}\n"
        "In Claude Code, type it with the `!` prefix: the approval is yours, never the agent's. "
        f"Then build it with `antstreet resume {run}`."
    )
    return True


def _awaiting(events: Sequence[Event]) -> bool:
    """`fund` left this run's term sheet waiting, and no investor has approved it since."""
    waited = any(
        e.event is EventType.STOPPED and e.actor == "boss" and e.data.get("reason") == AWAITING
        for e in events
    )
    return waited and not any(
        e.event is EventType.APPROVED and e.actor == "investor" for e in events
    )


def _approve(args: argparse.Namespace, project: Path, say: Say) -> int:
    """Show the term sheet `fund` left waiting, or, with `--sheet`, record the investor's approval
    of exactly the text shown. Spends nothing; `antstreet resume` builds it. With `--dispute`,
    record
    the investor's ruling on a dispute the run stopped on instead."""
    if (args.dispute is None) != (args.ruling is None) or (args.dispute and args.sheet):
        say("Rule on a dispute with both --dispute CHECK and --ruling drop|keep, without --sheet.")
        return EXIT_USAGE
    run = _find_run(args, project, say)
    if run is None:
        return EXIT_FAILED
    paths = RunPaths(project / RUNS_DIR / run)
    if args.dispute is not None:
        return _rule(args.dispute, args.ruling, run, paths, say)
    try:
        with paths.writer() as ledger:  # held from the reading to the approval
            events = paths.events()
            config = started_config(events)
            if config is None or not _awaiting(events):
                say(
                    f"Run {run} is not {AWAITING}: only a term sheet `antstreet fund` drafted "
                    f"with no "
                    "terminal to ask on, and not yet approved, is approved this way."
                )
                return EXIT_FAILED
            waited = [e.data for e in events if e.data.get("reason") == AWAITING][-1]
            untested, notes = waited.get("untested"), waited.get("notes")
            waivers = untested if isinstance(untested, dict) else {}
            setup = recorded_setup(events) or Setup((), DEFAULT_MODEL, None)
            policy = config.dispatch_policy()
            view = None
            if policy is not None:
                review = "critic" if "critic" in setup.roles else "off"
                level = dispatching.RunLevel(setup.model, review, config.held_out, config.parallel)
                view = dispatching.DispatchView(policy, level, config.policy.stall_slices, {})
            rules = paths.rules if paths.rules.is_file() else None
            spec_shown = spec_view(paths.rules, paths.checks, waivers) if rules else None
            if args.sheet is None:
                kept = notes if isinstance(notes, list) else []
                lines = [n for n in kept if isinstance(n, str)]
                ok = _show_pending(paths, run, view, spec_shown, lines, say)
                return EXIT_OK if ok else EXIT_FAILED
            held_dir = paths.held_out if held_out.hashes(paths.held_out) else None
            approve_shown(
                args.sheet,
                paths.root,
                paths.checks,
                ledger,
                run,
                held_out_dir=held_dir,
                view=view,
                spec_shown=spec_shown,
                rules_path=rules,
            )
    except LedgerLockedError:
        say(_held_by_another(run, "approve"))
        return EXIT_FAILED
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be approved: its ledger is damaged ({exc}).")
        return EXIT_FAILED
    except (NotApprovedError, TermSheetError, spec.SpecError) as exc:
        say(f"Not approved: {exc}. Nothing was written.")
        return EXIT_FAILED
    say(f"Approved run {run}. Build it with `antstreet resume {run}`.")
    return EXIT_OK


def _rule(check: str, ruling: str, run: str, paths: RunPaths, say: Say) -> int:
    """Record the investor's ruling on a dispute the run stopped on, signed like an approval.
    Only a check the run is waiting on can be ruled on, and only once."""
    try:
        with paths.writer() as ledger:  # held from the reading to the ruling
            events = paths.events()
            waiting = {d["check"]: d for d in rulings.awaited(events)}
            dispute = waiting.get(check)
            if dispute is None:
                listed = ", ".join(waiting) or "none"
                say(
                    f"Run {run} is not waiting for a ruling on {check!r} (waiting on: {listed}). "
                    "Nothing was written."
                )
                return EXIT_FAILED
            kind = rulings.DROPPED if ruling == "drop" else rulings.KEPT
            data = {"task": dispute["task"], "worker": dispute["worker"], "check": check}
            Recorder(ledger, run, events[-1].round)(
                "investor", EventType.RULED, data=data | {"ruling": kind}
            )
            left = [c for c in waiting if c != check]
    except LedgerLockedError:
        say(_held_by_another(run, "rule"))
        return EXIT_FAILED
    except LedgerCorruptError as exc:
        say(f"Run {run} cannot be ruled on: its ledger is damaged ({exc}).")
        return EXIT_FAILED
    say(f"Ruled on check {check} of run {run}: {kind}.")
    if left:
        say(f"Still waiting for your ruling on: {', '.join(left)}.")
    else:
        say(f"Continue with `antstreet resume {run}`.")
    return EXIT_OK


def _dispatch_refusal(args: argparse.Namespace) -> str | None:
    """Why the dispatch flags cannot be used together, before anything is spent."""
    if args.dispatch == "off":
        return "--max-tier needs --dispatch rules or cascade." if args.max_tier else None
    tier = dispatching.tier_of(args.model)
    if tier is None:
        return (
            f"--dispatch {args.dispatch} needs --model to be one of {', '.join(dispatching.TIERS)}."
        )
    top = args.max_tier or dispatching.DEFAULT_MAX_TIER
    if dispatching.rank(tier) > dispatching.rank(top):
        return f"--model {tier} is above --max-tier {top}; raise --max-tier."
    if args.reserve is not None:
        return (
            f"--reserve cannot be used with --dispatch {args.dispatch}: the reserve is per model."
        )
    return None


def _dispatch_policy(args: argparse.Namespace) -> dispatching.DispatchPolicy | None:
    if args.dispatch == "off":
        return None
    return dispatching.DispatchPolicy(
        args.max_tier or dispatching.DEFAULT_MAX_TIER, args.slice, args.dispatch == "cascade"
    )


def _spec_refusal(args: argparse.Namespace, roles: Sequence[str]) -> str | None:
    """Why `--spec` cannot be used with these options, or None. Checked before anything is spent."""
    if args.max_tasks != 1:
        return "--spec needs --max-tasks 1: the rules are covered by one builder's checks."
    if "system_designer" in roles and "tester" in roles:
        return (
            "--spec cannot be combined with the staged draft (--roles with system_designer and "
            "tester): its checks cite story criteria, not the idea's rules."
        )
    return None


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
    if isinstance(outcome, int) or outcome.stopped == rulings.RULING_AWAITED:
        return outcome  # no critic or demo on a build that waits for the investor's ruling
    try:
        return pipe.after_build(sheet, outcome, run, review_cycles=cycles, fix_micros=fix_micros)
    except KeyboardInterrupt:
        pipe.say(f"Interrupted. Nothing is lost: continue with `antstreet resume {pipe.run_id}`.")
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
            unattended=_unattended(ask),
        )
    except IsolationError as exc:
        say(f"Stopped: the worker did not start isolated ({exc}). Run `antstreet doctor`.")
    except ModelMismatchError as exc:
        say(f"Stopped: the wrong model ran ({exc}). The slice was booked; nothing more was spent.")
    except NotApprovedError as exc:
        say(f"Stopped: {exc}. Nothing was spent.")
    except KeyboardInterrupt:
        say(f"Interrupted. Nothing is lost: continue with `antstreet resume {run_id}`.")
        return EXIT_INTERRUPTED
    return EXIT_FAILED


def _finish(paths: RunPaths, outcome: FirmReport | int, say: Say) -> int:
    if isinstance(outcome, int):
        return outcome
    events = paths.events()
    text, unverified = _report_text(paths, events)
    (paths.root / "report.md").write_text(text, encoding="utf-8")
    say(text)
    if outcome.stopped == rulings.RULING_AWAITED:
        say(rulings.how_to_rule(paths.root.name, rulings.awaited(events)))
        say(f"Run folder: {paths.root}")
        return EXIT_AWAITING
    if outcome.stopped:
        say(f"Ended early: {outcome.stopped}")
        if not outcome.all_passed:
            say(f"To continue this run: `antstreet resume {paths.root.name}`")
    say(f"Run folder: {paths.root}  (built files: {paths.product})")
    if unverified:
        return EXIT_FAILED
    return EXIT_OK if outcome.all_passed else EXIT_INCOMPLETE


def _report_text(paths: RunPaths, events: Sequence[Event]) -> tuple[str, list[str]]:
    """The board report, with a failure line for each saved prompt that no longer matches the
    hash its slice recorded (only a run with dispatch on has any to check)."""
    text = render_report(build_report(events))
    if paths.investor_key is not None and (unsigned := unsigned_lines(paths.ledger)):
        text += (
            f"\nLedger: {unsigned} of {len(events)} lines are unsigned: either older than line "
            "signing or rewritten without the key; see docs/LEDGER.md.\n"
        )
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
    if _awaiting(events):
        say(f"Run {run} is {AWAITING}; nothing was built. Read it with `antstreet approve {run}`.")
        return EXIT_FAILED
    config = started_config(events)
    if config is None:
        say(f"Run {run} never got as far as hiring; start again with `antstreet fund`.")
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
    say(f"Continue with `antstreet resume {run}`.")
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
            else f"No runs under {runs}. Start one with `antstreet fund`."
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
    if args.json:
        state = {
            "run": run,
            "awaiting": _awaiting(events),
            "last_actor": last.actor,
            "last_event": str(last.event),
            "checks_passed": passed,
            "checks_total": len(report.checks),
            "spend_micros": report.total.cost_micros,
            "unknown_cost_events": unknown,
        }
        say(json.dumps(state))
        return EXIT_OK
    spend = dollars(report.total.cost_micros) + (f" + {unknown} unknown" if unknown else "")
    say(
        f"{run}: last event {last.actor} {last.event}; "
        f"{passed}/{len(report.checks)} checks passing; spend {spend} estimated"
    )
    return EXIT_OK


def _verify(args: argparse.Namespace, project: Path, say: Say) -> int:
    """Integrity only: the hash chain and signatures (`events()` raises unless they hold) and the
    saved prompts against their hashes. One line per problem; no model is ever called."""
    run = _find_run(args, project, say)
    if run is None:
        return EXIT_USAGE
    paths = RunPaths(project / RUNS_DIR / run)
    try:
        if args.adopt_unsigned and paths.investor_key is not None:
            adopted = adopt_unsigned(paths.ledger, paths.investor_key)
            say(
                f"Run {run}: adopted {adopted} unsigned lines as they are now; from here on they "
                "are anchored and every new line is signed."
            )
        events = paths.events()
    except LedgerLockedError:
        say(f"Run {run} is being written by another `boss` process; try again.")
        return EXIT_FAILED
    except (LedgerCorruptError, SigningError) as exc:
        say(f"Run {run} does not verify: {exc}. Do not trust it; restore the run folder.")
        return EXIT_FAILED
    if not events:
        say(f"Run {run} has an empty ledger.")
        return EXIT_FAILED
    problems = verify(paths, events)
    for problem in problems:
        say(f"Run {run}: {problem}. Do not trust this run's report; restore {paths.root / 'logs'}.")
    if not problems:
        say(f"Run {run} verifies: {len(events)} events, chain and signatures intact.")
    return EXIT_FAILED if problems else EXIT_OK


def _audit(args: argparse.Namespace, environ: Mapping[str, str], ask: Ask, say: Say) -> int:
    """`antstreet audit plan | check | report`. Every refusal (a dirty tree, a ledger or approval
    that
    does not verify, a head off the base, a hostile repository) is exit 1 with the reason."""
    store = audit.store_root(environ)
    try:
        if args.audit_command == "plan":
            return _audit_plan(args, environ, store, ask, say)
        if args.audit_command == "check":
            return _audit_check(args, store, say)
        return _audit_report(args, store, say)
    except KeyboardInterrupt:
        say("Interrupted.")
        return EXIT_INTERRUPTED
    except LedgerLockedError:
        say("Stopped: this audit run is being written by another `boss` process; try again.")
        return EXIT_FAILED
    except (
        audit.AuditError,
        NotApprovedError,
        LedgerCorruptError,
        SigningError,
        GitError,
        GateError,
        TermSheetError,
    ) as exc:
        say(f"Stopped: {exc}")
        return EXIT_FAILED


def _audit_plan(
    args: argparse.Namespace, environ: Mapping[str, str], store: Path, ask: Ask, say: Say
) -> int:
    done = audit.plan(
        Path(args.repo),
        Path(args.request),
        args.base,
        store=store,
        held_out_n=args.held_out,
        env=worker_env(environ),
        executable=environ.get(EXECUTABLE_VAR, CLI),
        boss_model=args.boss_model,
        ask=ask,
        say=say,
    )
    if done is None:
        say("Rejected. No checks were sealed.")
        return EXIT_FAILED
    say(
        f"Sealed audit run {done.run_id}: {done.counted} of {done.total} checks fail on the base "
        f"and will be counted.\nSeal: {done.seal}\nStore: {store}\n"
        "Record the seal where the agent cannot change it, and keep the store out of the agent's "
        "reach. When the agent says it is done, in the repo: "
        f"antstreet audit check {done.run_id} --claim done (the head defaults to HEAD)"
    )
    return EXIT_OK


def _audit_check(args: argparse.Namespace, store: Path, say: Say) -> int:
    # Only an omitted run means the latest; one given, even empty, is checked as given.
    run = audit_report.run_ids(store, None, every=False)[0] if args.run is None else args.run
    verdict = audit_check.check(
        run,
        args.head,
        repo=Path(args.repo),
        store=store,
        claim=args.claim,
        claim_text=Path(args.claim_text) if args.claim_text else None,
        agent=args.agent,
        strength=not args.no_strength,
        max_mutants=args.max_mutants,
        strength_timeout_s=args.strength_timeout,
    )
    say(audit_check.render_check(verdict))
    return EXIT_INCOMPLETE if verdict.verdict in ("refuted", "inconclusive") else EXIT_OK


def _audit_report(args: argparse.Namespace, store: Path, say: Say) -> int:
    chosen = audit_report.run_ids(store, args.run, every=args.all)
    say(audit_report.render(audit_report.collect(store, chosen, args.agent)))
    return EXIT_OK


def _doctor(args: argparse.Namespace, project: Path, environ: Mapping[str, str], say: Say) -> int:
    from antstreet.doctor import render_doctor, run_doctor

    checks = run_doctor(
        worker_env(environ), project, live=args.live, executable=environ.get(EXECUTABLE_VAR, CLI)
    )
    say(render_doctor(checks))
    return EXIT_OK if all(c.ok for c in checks) else EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
