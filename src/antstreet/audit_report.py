"""`antstreet audit report`: the gate's verdicts, run by run and in aggregate.

Only `audited` events written by the gate and verified by the store's key are read
(`RunPaths.events` refuses a ledger with a forged or edited one). A later verdict on the same head,
run and agent replaces an earlier one. The false-pass rate is refuted / (claimed done and not
inconclusive), with a Wilson interval, per agent label and per claim mode: a pre-registered claim
and a post-hoc one are never pooled, because a post-hoc audit may have been written after the work
was seen.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from antstreet.audit import AuditError, run_paths, runs_in
from antstreet.audit_check import MODES, VERDICTS
from antstreet.ledger import audited
from antstreet.stats import wilson_interval

Z95 = 1.959964  # the normal quantile for a two-sided 95% interval
NO_AGENT = "(no label)"
RECALL_FLOOR_NOTE = (
    "A floor, not a measurement of the agent: an unrefuted claim is not a correct one. The sealed "
    "checks catch only some wrong implementations (about 60% in the design's working figure), so "
    "the true false-pass rate is at least what is shown."
)
POST_HOC_NOTE = (
    "Post-hoc rows are not pre-registered: some commit predates the seal, and commit dates are set "
    "by the committer and can be forged. They are never added to the pre-registered rows."
)


@dataclass(frozen=True, slots=True)
class Observation:
    run: str
    agent: str
    head: str
    verdict: str
    claim_mode: str
    counted: int
    failed: tuple[str, ...]
    mutants: int = 0  # 0: strength not measured (an older event, or `--no-strength`)
    killed: tuple[tuple[str, int], ...] = ()


def wilson(refuted: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    """The Wilson score interval for `refuted` of `n`; None when there is nothing to divide."""
    if n <= 0 or not 0 <= refuted <= n:
        return None
    return wilson_interval(refuted, n, z)


def collect(store: Path, run_ids: list[str], agent: str | None = None) -> list[Observation]:
    """The verdicts of these runs, oldest first. A ledger the key does not vouch for raises its
    own error: a report built on part of the store would hide the part that was tampered with."""
    found: dict[tuple[str, str, str], Observation] = {}
    for run_id in run_ids:
        for event in audited(run_paths(store, run_id).events()):
            data = event.data
            label = data.get("agent") if isinstance(data.get("agent"), str) else NO_AGENT
            observation = Observation(
                run=run_id,
                agent=str(label),
                head=str(data.get("head", "")),
                verdict=str(data.get("verdict", "")),
                claim_mode=str(data.get("claim_mode", "")),
                counted=int(data.get("counted", 0) or 0),
                failed=tuple(str(i) for i in data.get("failed") or ()),
                **_strength(data.get("strength")),
            )
            found.pop((run_id, observation.agent, observation.head), None)  # a later one replaces
            found[(run_id, observation.agent, observation.head)] = observation
    return [o for o in found.values() if agent is None or o.agent == agent]


def _strength(raw: object) -> dict[str, Any]:
    """The strength of an `audited` event. Events written before it was recorded have none."""
    if not isinstance(raw, dict) or not isinstance(raw.get("killed"), dict):
        return {}
    killed = tuple((str(i), k) for i, k in raw["killed"].items() if isinstance(k, int))
    mutants = raw.get("mutants")
    return {"mutants": mutants, "killed": killed} if isinstance(mutants, int) else {}


def run_ids(store: Path, run: str | None, *, every: bool) -> list[str]:
    known = runs_in(store)
    if every:
        return known
    chosen = run or (known[-1] if known else None)
    if chosen is None or chosen not in known:
        where = f"No audit run {chosen!r}" if chosen else "No audit runs"
        raise AuditError(f"{where} under {store}. Seal checks with `antstreet audit plan`.")
    return [chosen]


def render(observations: list[Observation]) -> str:
    if not observations:
        return "No audit verdicts yet. Run `antstreet audit check RUN --head REF --claim done`."
    lines: list[str] = []
    for run in dict.fromkeys(o.run for o in observations):
        lines.append(f"Run {run}")
        for o in (o for o in observations if o.run == run):
            detail = f", failed {', '.join(o.failed)} of {o.counted} counted" if o.failed else ""
            if o.verdict in ("unrefuted", "inconclusive") and not o.failed:
                detail = f", {o.counted} counted"
            lines.append(
                f"  {o.head[:12]} [{o.agent}] {o.claim_mode.replace('_', '-')}: {o.verdict}{detail}"
            )
            if o.mutants:
                bites = ", ".join(f"{i} {k}" + (" WEAK" if k == 0 else "") for i, k in o.killed)
                lines.append(f"    check strength, kills of {o.mutants} mutants: {bites}")
    lines += ["", _aggregate(observations)]
    lines += ["", RECALL_FLOOR_NOTE]
    if any(o.claim_mode == "post_hoc" for o in observations):
        lines.append(POST_HOC_NOTE)
    return "\n".join(lines)


def _aggregate(observations: list[Observation]) -> str:
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: dict.fromkeys(VERDICTS, 0))
    for o in observations:
        if o.verdict in VERDICTS:
            groups[(o.agent, o.claim_mode)][o.verdict] += 1
    header = (
        "False-pass rate = refuted / (claimed done and not inconclusive), 95% Wilson interval; "
        "pre-registered and post-hoc rows are separate."
    )
    rows = [
        "agent | mode | refuted | unrefuted | inconclusive | no claim | false-pass | 95% interval",
        "---|---|---|---|---|---|---|---",
    ]
    order = sorted(groups, key=lambda k: (k[0], MODES.index(k[1]) if k[1] in MODES else 9))
    for agent, mode in order:
        c = groups[(agent, mode)]
        n = c["refuted"] + c["unrefuted"]
        interval = wilson(c["refuted"], n)
        rate = f"{c['refuted'] / n:.0%} ({c['refuted']}/{n})" if n else "n/a (0 judged)"
        span = f"{interval[0]:.0%} to {interval[1]:.0%}" if interval else "n/a"
        rows.append(
            f"{agent} | {mode.replace('_', '-')} | {c['refuted']} | {c['unrefuted']} | "
            f"{c['inconclusive']} | {c['no_claim']} | {rate} | {span}"
        )
    return "\n".join([header, *rows])
