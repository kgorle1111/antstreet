"""Per-task dispatch: which model and effort each task's worker runs on, and the one-agent route.

Everything here is a pure function of the term sheet and the run's flags. The boss's draft never
chooses a model: `plan_dispatch` fills the sheet from fixed rules, the investor reads the result in
the term sheet and may edit it, and `dispatch_problems` refuses any value outside the whitelist,
before the sheet can be approved and again before a worker is hired. A worker is stepped up
(`escalate`) only when the gate fired its predecessor for no progress or a slice limit.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from boss import budget
from boss.ledger import Event, EventType
from boss.redact import safe_text
from boss.termsheet import Dispatch, TermSheet
from boss.worker import usd

TIERS = ("haiku", "sonnet", "opus")  # cheapest first; a step up is the next one
DEFAULT_MAX_TIER = "sonnet"  # opus only when the investor passes --max-tier opus
AGENTS = ("builder",)  # the roles in src/boss/roles are run-level steps, not per-task agents
EFFORTS = ("off", "default", "high")
HIGH_THINKING_TOKENS = 8_000  # kn: unmeasured; the one number to tune after E6
NO_ESCALATION = "none"
MAX_TASK_WORKERS = (1, 2)  # 2 is firm.MAX_WORKERS_PER_TASK, pinned by a test
ROUTE_ONE_AGENT, ROUTE_FIRM = "one_agent", "firm"
ROUTES = (ROUTE_ONE_AGENT, ROUTE_FIRM)
ESCALATING_FIRINGS = frozenset({"no progress", "slice limit"})  # the gate's own words (rule.decide)
_SHOWN_FILES = 6


@dataclass(frozen=True, slots=True)
class DispatchPolicy:
    """What the run allows. Built from the flags; recorded in `started.config` so a resume and the
    hire-time check use the same one the investor saw."""

    max_tier: str
    slice_micros: int  # the run's --slice

    def __post_init__(self) -> None:
        if self.max_tier not in TIERS:
            raise ValueError(f"max_tier must be one of {TIERS}, got {self.max_tier!r}")


def rank(tier: str) -> int:
    return TIERS.index(tier)


def tier_of(model: str) -> str | None:
    """The tier of a model alias or full id, None when it is none of the whitelisted families."""
    name = model.lower()
    return next((t for t in TIERS if t in name), None)


def thinking_for(effort: str, default: int | None) -> int | None:
    """The CLI thinking budget of an effort: off is 0, default is the run's own, high is fixed."""
    return {"off": 0, "default": default, "high": HIGH_THINKING_TOKENS}[effort]


# --- the route --------------------------------------------------------------------------------


def files_of(sheet: TermSheet) -> list[str]:
    """Every distinct path a task owns, normalised and sorted."""
    return sorted({PurePosixPath(p).as_posix() for t in sheet.tasks for p in t.paths})


def route_of(sheet: TermSheet) -> str:
    """One agent when everything the sheet builds is one file; the firm otherwise. Deterministic:
    the same sheet gives the same route. The sheet's tasks may not share a path (structural
    validation refuses it), so in a valid sheet this means one task on one file."""
    files = files_of(sheet)
    one_file = len(files) == 1 and files[0] != "." and bool(PurePosixPath(files[0]).suffix)
    return ROUTE_ONE_AGENT if one_file else ROUTE_FIRM


def route_text(sheet: TermSheet, route: str) -> str:
    if route == ROUTE_ONE_AGENT:
        n = len(sheet.checks)
        return f"Route: one agent (one file, {n} check{'s' * (n != 1)})"
    files = [safe_text(f, limit=60) for f in files_of(sheet)]
    shown = ", ".join(files[:_SHOWN_FILES]) + (", ..." if len(files) > _SHOWN_FILES else "")
    n = len(sheet.tasks)
    return f"Route: firm ({n} task{'s' * (n != 1)}, files {shown})"


# --- the whitelist ----------------------------------------------------------------------------


def _shown(value: object) -> str:
    return safe_text(repr(value), limit=40)


def dispatch_problems(sheet: TermSheet, policy: DispatchPolicy | None) -> list[str]:
    """Every reason the sheet's dispatch cannot run. `policy` None is `--dispatch off`: then a sheet
    that carries dispatch is refused, so an edited sheet cannot route a worker with the flag off."""
    if policy is None:
        found = [
            f"task {t.id} carries dispatch, but --dispatch is off"
            for t in sheet.tasks
            if t.dispatch
        ]
        if sheet.route is not None:
            found.append("the sheet carries a route, but --dispatch is off")
        return found
    problems = _route_problems(sheet)
    ids = {t.id for t in sheet.tasks}
    for task in sheet.tasks:
        if task.dispatch is None:
            problems.append(f"task {task.id} has no dispatch, and --dispatch is on")
        else:
            problems += _task_problems(sheet, task.id, task.dispatch, policy, ids)
    return problems


def _route_problems(sheet: TermSheet) -> list[str]:
    if sheet.route not in ROUTES:
        return [f"route must be one of {list(ROUTES)}, got {_shown(sheet.route)}"]
    if sheet.route == ROUTE_ONE_AGENT and route_of(sheet) != ROUTE_ONE_AGENT:
        return [
            "route 'one_agent' needs everything built in one file; this sheet has "
            f"{len(sheet.tasks)} task(s) over {', '.join(files_of(sheet))}. Set the route to "
            "'firm', or merge the tasks into one first."
        ]
    return []


def _task_problems(
    sheet: TermSheet, task_id: str, d: Dispatch, policy: DispatchPolicy, ids: set[str]
) -> list[str]:
    from boss.roles.builders import PROFILES  # builders imports boss.boss, which imports termsheet

    p: list[str] = []
    at = f"task {task_id} dispatch"
    if d.agent not in AGENTS:
        p.append(f"{at}: agent {_shown(d.agent)} is not one of {list(AGENTS)}")
    if d.profile is not None and d.profile not in {x.name for x in PROFILES}:
        p.append(f"{at}: profile {_shown(d.profile)} is not a known profile")
    tier_ok = d.tier in TIERS and rank(d.tier) <= rank(policy.max_tier)
    if not tier_ok:
        p.append(
            f"{at}: tier {_shown(d.tier)} is not one of {list(TIERS[: rank(policy.max_tier) + 1])}"
        )
    if d.effort not in EFFORTS:
        p.append(f"{at}: effort {_shown(d.effort)} is not one of {list(EFFORTS)}")
    p += _escalation_problems(at, d, policy, tier_ok)
    if type(d.max_workers) is not int or d.max_workers not in MAX_TASK_WORKERS:
        p.append(
            f"{at}: max_workers {_shown(d.max_workers)} is not one of {list(MAX_TASK_WORKERS)}"
        )
    sm = d.slice_micros
    if sm is not None and (
        type(sm) is not int or not budget.MIN_SLICE_MICROS <= sm <= policy.slice_micros
    ):
        p.append(
            f"{at}: slice_micros {_shown(sm)} must be null or a whole number from "
            f"{budget.MIN_SLICE_MICROS} to the run's slice, {policy.slice_micros}"
        )
    for read in d.reads:
        if read not in ids or read == task_id:
            p.append(f"{at}: reads {_shown(read)}, which is not another task of the sheet")
    if len(set(d.reads)) != len(d.reads):
        p.append(f"{at}: reads repeats a task")
    if tier_ok and type(sm) in (int, type(None)):
        need = budget.min_round_budget(budget.reserve_for(d.tier))
        thinnest = min((r.budget_micros for r in sheet.rounds), default=0)
        if thinnest < need:
            p.append(
                f"{at}: a {d.tier} slice needs a round of at least ${usd(need)} "
                f"(reserve plus slice); the thinnest round has ${usd(thinnest)}"
            )
    return p


def _escalation_problems(at: str, d: Dispatch, policy: DispatchPolicy, tier_ok: bool) -> list[str]:
    if d.escalate_to == NO_ESCALATION:
        return []
    if d.escalate_to not in TIERS or rank(d.escalate_to) > rank(policy.max_tier):
        allowed = [NO_ESCALATION, *TIERS[: rank(policy.max_tier) + 1]]
        return [f"{at}: escalate_to {_shown(d.escalate_to)} is not one of {allowed}"]
    if tier_ok and rank(d.escalate_to) < rank(d.tier):
        return [f"{at}: escalate_to {d.escalate_to} is below the task's own tier {d.tier}"]
    return []


# --- planning ---------------------------------------------------------------------------------


def fits(tier: str, remaining_micros: int, slice_micros: int) -> bool:
    """Whether a worker on `tier` can be funded: its slice cap, after the tier's reserve, is at
    least half the run's slice (a smaller one is a worker that cannot do a turn's work)."""
    cap = budget.next_slice_cap(
        remaining_micros, slice_micros=slice_micros, reserve_micros=budget.reserve_for(tier)
    )
    return cap is not None and cap >= slice_micros // 2


def needed_to_fit(tier: str, slice_micros: int) -> int:
    return budget.reserve_for(tier) + slice_micros // 2


def plan_dispatch(
    sheet: TermSheet,
    *,
    tier: str,
    profile: str | None,
    policy: DispatchPolicy,
    reads: Mapping[str, tuple[str, ...]],
) -> TermSheet:
    """The sheet with its route and every task's dispatch filled from the rules. Today every rule
    resolves to one answer: the run's own tier, default effort, a step up one tier if the thinnest
    round can fund it, two workers per task (one when the one-agent route has no step to offer)."""
    route = route_of(sheet)
    thinnest = min(r.budget_micros for r in sheet.rounds)
    up = TIERS[rank(tier) + 1] if rank(tier) < rank(policy.max_tier) else None
    if up is None:
        escalate_to = tier  # the top tier: only the effort can step up
    else:
        escalate_to = up if fits(up, thinnest, policy.slice_micros) else NO_ESCALATION
    workers = 1 if route == ROUTE_ONE_AGENT and escalate_to == NO_ESCALATION else 2
    tasks = tuple(
        dataclasses.replace(
            t,
            dispatch=Dispatch(
                "builder", profile, tier, "default", escalate_to, workers, None, reads.get(t.id, ())
            ),
        )
        for t in sheet.tasks
    )
    return dataclasses.replace(sheet, tasks=tasks, route=route)


@dataclass(frozen=True, slots=True)
class Step:
    tier: str
    effort: str
    changed: bool
    refused: str | None  # why the step the task was allowed was not taken


def escalate(
    tier: str,
    effort: str,
    *,
    escalate_to: str,
    max_tier: str,
    remaining_micros: int,
    slice_micros: int,
) -> Step:
    """One step up: the next tier if the task allows it and the round can fund it; else the effort
    from `default` to `high`; else nothing, with the reason. Never more than one step."""
    if escalate_to == NO_ESCALATION:
        return Step(tier, effort, False, "stepping up is off for this task")
    ceiling = min(rank(escalate_to), rank(max_tier))
    refused = None
    if rank(tier) < ceiling:
        up = TIERS[rank(tier) + 1]
        if fits(up, remaining_micros, slice_micros):
            return Step(up, effort, True, None)
        refused = (
            f"{up} needs ${usd(needed_to_fit(up, slice_micros))} free in the round; "
            f"${usd(max(remaining_micros, 0))} is left"
        )
    if effort == "default":
        return Step(tier, "high", True, refused)
    return Step(tier, effort, False, refused or "already at the highest step this task allows")


@dataclass(frozen=True, slots=True)
class Hire:
    """What one worker is hired on, and why. `data()` is what the `hired` event records."""

    tier: str
    effort: str
    why: str
    from_tier: str | None = None
    refused: str | None = None

    def data(self) -> dict[str, str]:
        out = {"tier": self.tier, "effort": self.effort, "why": self.why}
        if self.from_tier is not None:
            out["from_tier"] = self.from_tier
        if self.refused is not None:
            out["refused"] = self.refused
        return out


def first_hire(d: Dispatch) -> Hire:
    return Hire(d.tier, d.effort, "term sheet")


def replacement_hire(
    d: Dispatch,
    previous: Hire,
    *,
    fired_for: str,
    stalled_slices: int,
    max_tier: str,
    remaining_micros: int,
    slice_micros: int,
    one_agent: bool,
) -> Hire | None:
    """Who replaces a fired worker, or None for nobody. A step up happens only for a firing the
    gate decided on evidence (`ESCALATING_FIRINGS`). On the one-agent route a replacement that is
    not stronger is not worth paying for, so there is none; in the firm it is hired as before."""
    if fired_for in ESCALATING_FIRINGS:
        step = escalate(
            previous.tier,
            previous.effort,
            escalate_to=d.escalate_to,
            max_tier=max_tier,
            remaining_micros=remaining_micros,
            slice_micros=slice_micros,
        )
    else:
        step = Step(previous.tier, previous.effort, False, "this firing does not step a worker up")
    if one_agent and not step.changed:
        return None
    why = f"predecessor fired: {fired_for}, {stalled_slices} stalled slices"
    return Hire(step.tier, step.effort, why, previous.tier, step.refused)


def worst_case_micros(sheet: TermSheet, policy: DispatchPolicy, stall_slices: int) -> int:
    """A cap on what stepping every task up can cost: per task, the slices before the rule fires
    a stalled worker, then one slice of its replacement, each priced at its cap plus one reserve
    (the most a slice can overshoot). The round budgets still stop the run first."""
    total = 0
    for task in sheet.tasks:
        d = task.dispatch
        if d is None:
            continue
        cap = policy.slice_micros if d.slice_micros is None else d.slice_micros
        total += stall_slices * (cap + budget.reserve_for(d.tier))
        if d.escalate_to != NO_ESCALATION and d.max_workers == 2:
            after = TIERS[min(rank(d.tier) + 1, rank(d.escalate_to))]
            total += cap + budget.reserve_for(after)
        elif d.max_workers == 2 and sheet.route != ROUTE_ONE_AGENT:
            total += cap + budget.reserve_for(d.tier)
    return total


# --- what the investor reads ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunLevel:
    """The dispatch choices that belong to the whole run, not to a task: shown, not per-task."""

    draft_model: str
    review: str
    held_out: int
    parallel: int


@dataclass(frozen=True, slots=True)
class DispatchView:
    policy: DispatchPolicy
    run: RunLevel
    stall_slices: int
    contexts: Mapping[str, int]  # task id -> characters of its first brief


def _money(micros: int) -> str:
    return f"${micros / 1_000_000:.2f}" if micros >= 10_000 else f"${micros / 1_000_000:.3f}"


def _if_fired(sheet: TermSheet, d: Dispatch, view: DispatchView) -> str:
    if d.escalate_to == NO_ESCALATION:
        up = rank(d.tier) + 1
        if up < len(TIERS) and up <= rank(view.policy.max_tier):
            thinnest = min(r.budget_micros for r in sheet.rounds)
            if not fits(TIERS[up], thinnest, view.policy.slice_micros):
                need = _money(needed_to_fit(TIERS[up], view.policy.slice_micros))
                return f"stays {d.tier} (a round of {need} would allow {TIERS[up]})"
        return "none (one agent)" if sheet.route == ROUTE_ONE_AGENT else "same model"
    up_tier = TIERS[min(rank(d.tier) + 1, rank(d.escalate_to))]
    step = up_tier if up_tier != d.tier else f"{d.tier}/high"
    return f"{step}, once"


def render_table(sheet: TermSheet, view: DispatchView) -> list[str]:
    """The route line and the dispatch table, as lines for `approval.render`."""
    route = sheet.route if sheet.route in ROUTES else ROUTE_FIRM
    rows = [("task", "agent", "model", "effort", "if fired", "context", "slice cap")]
    first_round = min(r.budget_micros for r in sheet.rounds)
    for task in sheet.tasks:
        d = task.dispatch
        if d is None:
            continue
        cap = budget.next_slice_cap(
            first_round,
            slice_micros=d.slice_micros or view.policy.slice_micros,
            reserve_micros=budget.reserve_for(d.tier) if d.tier in TIERS else budget.RESERVE_MICROS,
        )
        chars = view.contexts.get(task.id)
        rows.append(
            (
                task.id,
                safe_text(d.agent, limit=12),
                safe_text(d.tier, limit=8),
                safe_text(d.effort, limit=8),
                _if_fired(sheet, d, view),
                "-" if chars is None else f"~{chars / 1000:.1f}k chars",
                "none" if cap is None else _money(cap),
            )
        )
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = [route_text(sheet, route), ""]
    lines.append(
        'DISPATCH (change it by editing "dispatch" in term_sheet.json, then choose [e]dit)'
    )
    lines += ["  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip() for r in rows]
    run = view.run
    held = "off" if not run.held_out else str(run.held_out)
    lines.append(
        f"Run level: draft {safe_text(run.draft_model, limit=30)} | review {run.review} | "
        f"held-out {held} | parallel {run.parallel}"
    )
    worst = worst_case_micros(sheet, view.policy, view.stall_slices)
    budget_total = sum(r.budget_micros for r in sheet.rounds)
    over = (
        "  (OVER the budget; the round budget still stops the run)" if worst > budget_total else ""
    )
    lines.append(
        f"Worst case if every task steps up: {_money(worst)} of {_money(budget_total)}"
        f" ({view.stall_slices} slices, then one at the new price){over}"
    )
    return lines


# --- reading the ledger -----------------------------------------------------------------------


def recorded_hire(events: Sequence[Event], worker: str) -> tuple[str, Hire | None]:
    """The model a worker was hired on and its dispatch record, as the ledger holds them. A resume
    runs the worker on this model, whatever the run's config says now."""
    for e in events:
        if e.event is EventType.HIRED and e.data.get("worker") == worker:
            raw = e.data.get("dispatch")
            hire = None
            if isinstance(raw, dict) and raw.get("tier") in TIERS and raw.get("effort") in EFFORTS:
                hire = Hire(
                    raw["tier"],
                    raw["effort"],
                    str(raw.get("why", "")),
                    raw.get("from_tier"),
                    raw.get("refused"),
                )
            return str(e.data.get("model", "")), hire
    raise KeyError(worker)


def reachable_reserve(sheet: TermSheet, max_tier: str) -> int:
    """The largest reserve among the tiers any task of the sheet can be run on, a step up
    included: what the run's spend ceiling must allow one overshoot of."""
    reserves = [budget.RESERVE_MICROS]
    for task in sheet.tasks:
        d = task.dispatch
        if d is None or d.tier not in TIERS:
            continue
        top = rank(d.tier)
        if d.escalate_to in TIERS:
            top = max(top, min(rank(d.escalate_to), rank(max_tier)))
        reserves += [budget.reserve_for(t) for t in TIERS[rank(d.tier) : top + 1]]
    return max(reserves)
