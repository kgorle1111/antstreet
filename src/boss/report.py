"""The board report. Every figure is computed from ledger events and nothing else.

Costs are the CLI's client-side estimates, so the report says "estimated" and keeps events whose
cost is unknown as a separate count rather than folding them into the total as zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from boss.ledger import Event, EventType, Totals, total, totals_by

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
    notes: list[str] = field(default_factory=list)


def build_report(events: Sequence[Event]) -> Report:
    if not events:
        raise ValueError("cannot report on an empty ledger")
    runs = {e.run for e in events}
    if len(runs) != 1:
        raise ValueError(f"ledger mixes runs: {sorted(runs)}")

    latest_check: dict[str, CheckLine] = {}
    rounds: list[RoundLine] = []
    for e in events:
        if _missing(e):
            continue
        if e.event is EventType.CHECK_RESULT:
            line = CheckLine(e.data["check"], e.data["status"], e.data.get("detail", ""))
            latest_check[line.check] = line  # a later gate run supersedes an earlier one
        elif e.event is EventType.ROUND_CLOSED:
            rounds.append(RoundLine(e.round, e.data["passed"], e.data["total"], e.data["unlocked"]))

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
        notes=[_note(e) for e in events if e.event in _NOTABLE]
        + [_incomplete_note(e) for e in events if _missing(e)],
    )


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
    out += [f"  {c.check}  {c.status:<8} {c.detail}" for c in report.checks] or ["  none run"]

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
    if report.disputes:
        out += ["", "Disputed checks (yours to rule on; a disputed check never counts as passing)"]
        out += [f'  {d.check} by {d.worker}: "{d.reason}"' for d in report.disputes]
    if report.notes:
        out += ["", "Notes"] + [f"  {n}" for n in report.notes]
    return "\n".join(out) + "\n"


def _money(t: Totals) -> str:
    unknown = (
        f" + {t.unknown_cost_events} event(s) of unknown cost" if t.unknown_cost_events else ""
    )
    return dollars(t.cost_micros) + unknown


def _tokens(t: Totals) -> str:
    return f"tokens in {t.tokens_in:,} / out {t.tokens_out:,} / cached {t.tokens_cached:,}"
