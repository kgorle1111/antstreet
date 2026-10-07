"""Offline replay of a firing policy over ledgers recorded without firing.

Each worker's recorded history is walked one slice at a time through the rule; the first FIRE
verdict is the firing point and every later recorded slice is spend the policy would have saved.
The walk stops without a firing at the first DONE (every check passes: live, the task is finished
and the worker is never funded again) and at the first ESCALATE (blocked, refusal: live, the task
is set aside for the investor and the worker is never funded again), so nothing after either is a
saving.
RETRY (an infrastructure slice) is uncounted and the walk goes on, as the live worker does.
Unknown slice costs count as 0 on both sides of the saving, so saved and total are lower bounds.
A false firing needs a later slice that passes a check no slice up to the firing point had passed.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from boss import rule
from boss.ledger import Event, EventType, LedgerError
from boss.report import dollars
from boss.rule import Decision, FiringPolicy, SliceRecord, Verdict
from boss.rundir import RunPaths
from boss.state import slice_history

Decide = Callable[[frozenset[str], Sequence[SliceRecord], FiringPolicy], Verdict]

CLOSING = "False firings are workers the rule would have stopped that later passed a new check."


@dataclass(frozen=True, slots=True)
class WorkerReplay:
    worker: str
    slices: int  # slices the worker actually ran
    fired_after: int | None  # slice number after which the policy says FIRE; None if never
    saved_micros: int  # known cost of the slices after the firing point
    false_firing: bool  # a later slice passed a check no slice up to the firing point had passed
    lost_completion: bool  # a later slice had every task check passing


@dataclass(frozen=True, slots=True)
class PolicyResult:
    policy: FiringPolicy
    workers: int
    fired: int
    false_firings: int
    lost_completions: int
    saved_micros: int
    total_micros: int  # known cost of every slice of every worker


def task_checks_by_worker(events: Sequence[Event]) -> dict[str, frozenset[str]]:
    """Every check id the gate reported for each worker, whatever its status."""
    found: dict[str, set[str]] = {}
    for e in events:
        if e.event is EventType.CHECK_RESULT and "worker" in e.data:
            found.setdefault(str(e.data["worker"]), set()).add(str(e.data["check"]))
    return {worker: frozenset(ids) for worker, ids in found.items()}


def _known(records: Sequence[SliceRecord]) -> int:
    return sum(r.cost_micros or 0 for r in records)


def replay_worker(
    worker: str,
    checks: frozenset[str],
    history: Sequence[SliceRecord],
    policy: FiringPolicy,
    decide: Decide,
) -> WorkerReplay:
    for n in range(1, len(history) + 1):
        decision = decide(checks, history[:n], policy).decision
        if decision in (Decision.DONE, Decision.ESCALATE):
            break
        if decision is not Decision.FIRE:
            continue
        before, later = history[:n], history[n:]
        passed_before = frozenset().union(*(r.passing for r in before))
        return WorkerReplay(
            worker=worker,
            slices=len(history),
            fired_after=before[-1].slice,
            saved_micros=_known(later),
            false_firing=any(r.passing - passed_before for r in later),
            lost_completion=bool(checks) and any(checks <= r.passing for r in later),
        )
    return WorkerReplay(worker, len(history), None, 0, False, False)


def replay_runs(
    runs: Sequence[Sequence[Event]],
    policies: Sequence[FiringPolicy],
    decide: Decide = rule.decide,
) -> list[PolicyResult]:
    """One result per policy over every worker that ran a slice and has check results."""
    recorded: list[tuple[str, frozenset[str], list[SliceRecord]]] = []
    for events in runs:
        checks = task_checks_by_worker(events)
        for worker, history in slice_history(events).items():
            if worker in checks and history:
                recorded.append((worker, checks[worker], history))

    total = sum(_known(history) for _, _, history in recorded)
    results = []
    for policy in policies:
        replays = [replay_worker(w, c, h, policy, decide) for w, c, h in recorded]
        results.append(
            PolicyResult(
                policy=policy,
                workers=len(replays),
                fired=sum(r.fired_after is not None for r in replays),
                false_firings=sum(r.false_firing for r in replays),
                lost_completions=sum(r.lost_completion for r in replays),
                saved_micros=sum(r.saved_micros for r in replays),
                total_micros=total,
            )
        )
    return results


def _share(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def render_replay(results: Sequence[PolicyResult]) -> str:
    rows = [
        "| stall | max slices | workers | fired | false firings | lost completions | saved |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        rows.append(
            f"| {r.policy.stall_slices} | {r.policy.max_slices} | {r.workers} | {r.fired} "
            f"| {r.false_firings} ({_share(r.false_firings, r.fired)}) | {r.lost_completions} "
            f"| {dollars(r.saved_micros)} ({_share(r.saved_micros, r.total_micros)}) |"
        )
    return "\n".join(rows) + "\n\n" + CLOSING + "\n"


def main(argv: Sequence[str] | None = None, decide: Decide = rule.decide) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.replay")
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--stall", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--max-slices", type=int, nargs="+", default=[4, 6, 8])
    args = parser.parse_args(argv)
    try:
        policies = [FiringPolicy(s, m) for s, m in itertools.product(args.stall, args.max_slices)]
    except ValueError as exc:
        parser.error(str(exc))

    runs = []
    for path in sorted(args.results_dir.rglob("ledger.jsonl")):
        try:
            runs.append(RunPaths(path.parent).events())
        except (LedgerError, OSError, UnicodeDecodeError) as exc:
            print(f"cannot read ledger {path}: {exc}", file=sys.stderr)
            return 1
    runs = [events for events in runs if any(e.event is EventType.SLICE_END for e in events)]
    if not runs:
        print(f"no ledger with slice data under {args.results_dir}", file=sys.stderr)
        return 1
    print(render_replay(replay_runs(runs, policies, decide)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
