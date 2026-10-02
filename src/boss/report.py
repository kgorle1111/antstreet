"""The board report. Every figure is computed from ledger events and nothing else.

Costs are the CLI's client-side estimates, so the report says "estimated" and keeps events whose
cost is unknown as a separate count rather than folding them into the total as zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from boss.held_out import EXAMINER_ACTOR, MANIFEST
from boss.held_out import SCOPE as HELD_OUT_SCOPE
from boss.ledger import Event, EventType, Totals, total, totals_by
from boss.redact import safe_text

MAX_DETAIL_CHARS = 300
_NOTABLE = (
    EventType.FIRED,
    EventType.REASSIGNED,
    EventType.ABANDONED,
    EventType.BLOCKED,
    EventType.RULED,
    EventType.RESUMED,
    EventType.PAUSED,
    EventType.ERROR,
    EventType.STOPPED,
)
# The ledger does not constrain `data`, and a report is how a damaged run gets inspected: an event
# missing these keys is listed in the notes as incomplete, never indexed and never dropped silently.
_REQUIRED = {
    EventType.CHECK_RESULT: ("check", "status"),
    EventType.ROUND_CLOSED: ("passed", "total", "unlocked"),
    EventType.HIRED: ("worker",),
    EventType.DISPUTED: ("check",),
    EventType.ROLE_CALL: ("role", "outcome"),
}


@dataclass(frozen=True, slots=True)
class CheckLine:
    check: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class WorkerLine:
    worker: str
    task: str
    model: str
    outcome: str
    status: str
    reason: str
    slices: int


@dataclass(frozen=True, slots=True)
class DisputeLine:
    check: str
    worker: str
    reason: str


@dataclass(frozen=True, slots=True)
class RoleLine:
    role: str
    outcome: str  # how the call ended; "not_called" when it was refused before any call
    result: str  # ok, failed, or unused (its output was good but a later stage failed)
    cost_micros: int | None
    detail: str


@dataclass(frozen=True, slots=True)
class RoundLine:
    n: int
    passed: int
    total: int
    unlocked: bool


@dataclass(frozen=True, slots=True)
class Report:
    run: str
    approved: bool
    total: Totals
    by_actor: dict[str, Totals]
    rounds: list[RoundLine] = field(default_factory=list)
    checks: list[CheckLine] = field(default_factory=list)
    workers: list[WorkerLine] = field(default_factory=list)
    disputes: list[DisputeLine] = field(default_factory=list)
    roles: list[RoleLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    held_out: list[CheckLine] = field(
        default_factory=list
    )  # graded on the product, apart from checks
    held_out_written: int = 0  # held-out checks the investor approved
    held_out_summary: str | None = None  # the one line about them; None for a run that never asked


def build_report(events: Sequence[Event]) -> Report:
    if not events:
        raise ValueError("cannot report on an empty ledger")
    runs = {e.run for e in events}
    if len(runs) != 1:
        raise ValueError(f"ledger mixes runs: {sorted(runs)}")

    latest_check: dict[str, CheckLine] = {}
    latest_held_out: dict[str, CheckLine] = {}
    rounds: list[RoundLine] = []
    for e in events:
        if _missing(e):
            continue
        if e.event is EventType.CHECK_RESULT:
            line = CheckLine(e.data["check"], e.data["status"], e.data.get("detail", ""))
            # A later gate run supersedes an earlier one; a held-out result is never a visible
            # check's, whatever id it carries.
            held = e.data.get("scope") == HELD_OUT_SCOPE
            (latest_held_out if held else latest_check)[line.check] = line
        elif e.event is EventType.ROUND_CLOSED:
            rounds.append(RoundLine(e.round, e.data["passed"], e.data["total"], e.data["unlocked"]))

    held_out = [latest_held_out[k] for k in sorted(latest_held_out)]
    written, summary = _held_out_summary(events, held_out)
    return Report(
        run=events[0].run,
        approved=any(e.event is EventType.APPROVED and e.actor == "investor" for e in events),
        total=total(events),
        by_actor=totals_by(events, lambda e: e.actor),
        rounds=rounds,
        checks=[latest_check[k] for k in sorted(latest_check)],
        workers=_workers(events),
        disputes=[
            DisputeLine(e.data["check"], e.data.get("worker", ""), e.data.get("reason", ""))
            for e in events
            if e.event is EventType.DISPUTED and not _missing(e)
        ],
        roles=[
            RoleLine(
                str(e.data["role"]),
                str(e.data["outcome"]),
                str(e.data.get("result", "")),
                e.cost_micros,
                str(e.data.get("detail", "")),
            )
            for e in events
            if e.event is EventType.ROLE_CALL and not _missing(e)
        ],
        notes=[_note(e) for e in events if e.event in _NOTABLE]
        + [_incomplete_note(e) for e in events if _missing(e)],
        held_out=held_out,
        held_out_written=written,
        held_out_summary=summary,
    )


def _held_out_summary(
    events: Sequence[Event], graded: Sequence[CheckLine]
) -> tuple[int, str | None]:
    """How many held-out checks the investor approved, and the one line the report says about
    them: their result, or why a run that asked for them has none. None when it never asked."""
    hashes = [
        e.data["held_out_hashes"]
        for e in events
        if e.event is EventType.APPROVED
        and e.actor == "investor"
        and isinstance(e.data.get("held_out_hashes"), dict)
    ]
    written = len([k for k in hashes[-1] if k != MANIFEST]) if hashes else 0
    calls = [e for e in events if e.event is EventType.ROLE_CALL and e.actor == EXAMINER_ACTOR]
    started = next((e for e in events if e.event is EventType.STARTED), None)
    config = started.data.get("config") if started else None
    requested = config.get("held_out") if isinstance(config, dict) else 0
    count = max(written, len(graded))
    if count:
        passed = sum(c.status == "passed" for c in graded)
        unseen = "the workers never saw them"
        if not graded:
            done = (
                f"{count} approved, none graded on the product (the run ended before its verdict)"
            )
        elif len(graded) < count:
            done = f"{passed} of {count} passed on the product ({count - len(graded)} not graded)"
        else:
            done = f"{passed} of {count} passed on the product"
        return written, f"Held-out checks: {done}; {unseen}."
    if calls:
        return 0, _examiner_summary(calls[-1])
    if isinstance(requested, int) and not isinstance(requested, bool) and requested > 0:
        return 0, (
            f"Held-out checks: {requested} were requested, but no examiner call is recorded; "
            "the run had none."
        )
    return 0, None


def _examiner_summary(call: Event) -> str:
    """Why an examiner call left the run with no held-out checks. Its reasons are model text and
    exception text, so they pass `safe_text` on one line."""
    problems = call.data.get("problems")
    first = problems[0] if isinstance(problems, list) and problems else ""
    why = _detail(str(first)) or "no reason recorded"
    outcome = str(call.data.get("outcome", "unknown"))
    if call.data.get("kept"):
        return (
            f"Held-out checks: the examiner wrote {_detail(str(call.data['kept']))}, but the "
            "investor's approval does not cover them; none ran."
        )
    if outcome == "skipped":
        what = f"The examiner was not called ({why})"
    elif outcome == "completed":
        what = f"The examiner's output was not kept: {why}"
    else:
        what = f"The examiner's call ended {_detail(outcome)}: {why}"
    return f"Held-out checks: none. {what}; the run went on without them."


def _missing(event: Event) -> list[str]:
    return [k for k in _REQUIRED.get(event.event, ()) if k not in event.data]


def _incomplete_note(event: Event) -> str:
    return (
        f"round {event.round}: {event.actor} {event.event} is incomplete "
        f"(missing {', '.join(_missing(event))}); left out of the sections above"
    )


def _workers(events: Sequence[Event]) -> list[WorkerLine]:
    lines = []
    for hired in (e for e in events if e.event is EventType.HIRED and not _missing(e)):
        name = hired.data["worker"]
        ends = [e for e in events if e.event is EventType.SLICE_END and e.actor == f"worker:{name}"]
        last = ends[-1].data if ends else {}
        status = last.get("status") or {}
        lines.append(
            WorkerLine(
                worker=name,
                task=hired.data.get("task", ""),
                model=hired.data.get("model", ""),
                outcome=last.get("outcome", "no slice finished"),
                status=status.get("status", "none"),
                reason=status.get("reason", ""),
                slices=len(ends),
            )
        )
    return lines


def _note(event: Event) -> str:
    data = dict(event.data)
    evidence = data.pop("evidence", None)
    if isinstance(evidence, dict):  # a firing: summarise the rule's evidence in one phrase
        passing, missing = len(evidence.get("passing", [])), len(evidence.get("missing", []))
        data["after"] = (
            f"{evidence.get('counted_slices')} slices, {evidence.get('stalled_slices')} without "
            f"progress, {passing}/{passing + missing} checks passing"
        )
    detail = ", ".join(f"{k}={v}" for k, v in sorted(data.items()) if v is not None)
    return f"round {event.round}: {event.actor} {event.event}" + (f" ({detail})" if detail else "")


def dollars(micros: int) -> str:
    return f"${micros / 1_000_000:.4f}"


def render_report(report: Report) -> str:
    out = [f"BOARD REPORT  run {report.run}", ""]
    out.append("Approved by investor: " + ("yes" if report.approved else "NO"))
    for r in report.rounds:
        verdict = "next round unlocked" if r.unlocked else "not unlocked"
        out.append(f"Round {r.n}: {r.passed}/{r.total} checks passed, {verdict}")
    if not report.rounds:
        out.append("No round has closed.")

    out += ["", "Checks"]
    out += [f"  {c.check}  {c.status:<8} {_detail(c.detail)}" for c in report.checks] or [
        "  none run"
    ]

    if report.held_out_summary:
        out += ["", report.held_out_summary]
        out += [f"  {c.check}  {c.status:<8} {_detail(c.detail)}" for c in report.held_out]

    out += ["", "Spend (estimated by the CLI, not a bill)"]
    for actor in sorted(report.by_actor):
        t = report.by_actor[actor]
        if t.cost_micros or t.unknown_cost_events or t.tokens_in or t.tokens_out:
            out.append(f"  {actor:<12} {_money(t)}   {_tokens(t)}")
    out.append(f"  {'total':<12} {_money(report.total)}   {_tokens(report.total)}")

    out += ["", "Workers"]
    for w in report.workers:
        reason = f': "{w.reason}"' if w.reason else ""
        out.append(
            f"  {w.worker} on {w.task} ({w.model}): {w.outcome}, status {w.status}{reason}, "
            f"{w.slices} slice(s)"
        )
    if not report.workers:
        out.append("  none hired")
    if report.roles:
        out += ["", "Roles (each call, in order; their spend is in the lines above)"]
        for role in report.roles:
            cost = "unknown cost" if role.cost_micros is None else dollars(role.cost_micros)
            detail = f": {_detail(role.detail)}" if role.detail else ""
            how = f"{_detail(role.result) or '?'} ({_detail(role.outcome)})"
            out.append(f"  {_detail(role.role)}  {how}, {cost}{detail}")
    if report.disputes:
        out += ["", "Disputed checks (yours to rule on; a disputed check never counts as passing)"]
        out += [f'  {d.check} by {d.worker}: "{d.reason}"' for d in report.disputes]
    if report.notes:
        out += ["", "Notes"] + [f"  {n}" for n in report.notes]
    return "\n".join(out) + "\n"


def _detail(text: str) -> str:
    """Gate detail comes from a subprocess (a parse error quotes its input): one line, masked."""
    return safe_text(" ".join(str(text).split()), limit=MAX_DETAIL_CHARS)


def _money(t: Totals) -> str:
    unknown = (
        f" + {t.unknown_cost_events} event(s) of unknown cost" if t.unknown_cost_events else ""
    )
    return dollars(t.cost_micros) + unknown


def _tokens(t: Totals) -> str:
    return f"tokens in {t.tokens_in:,} / out {t.tokens_out:,} / cached {t.tokens_cached:,}"
