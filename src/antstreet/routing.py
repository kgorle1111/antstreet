"""Which tier a cascade starts on, chosen from what this project's own past runs recorded.

Escalation is not free: a task that fails on Haiku has paid for Haiku and then pays for Sonnet. So
the start tier of each kind of task is the one with the lowest expected cost, from the observed
verified-fail rate and mean cost per attempt of that kind and tier (`choose_start`). Where the
project has too few attempts of a kind (`MIN_SAMPLE`) a fixed prior stands in, and the dispatch
table says so. The data is read only from run folders whose ledger, term sheet and checks the
investor key vouches for (`read_runs`); a run that does not verify is left out and named, so a
doctored past run cannot steer a start tier.

Everything here is a pure function of the ledgers read. No model is called.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from antstreet import signing
from antstreet.approval import content_hashes
from antstreet.dispatch import ESCALATING_FIRINGS, TIERS, ladder, rank, rungs_from, tier_of
from antstreet.ledger import Event, EventType, LedgerError
from antstreet.report import _delivered
from antstreet.rundir import RunPaths
from antstreet.termsheet import Task, TermSheet, TermSheetError

MIN_SAMPLE = 5  # attempts of one kind and tier below which the prior is used, not the data
RUNS_DIR = Path(".boss") / "runs"
TERM_SHEET_FILE = "term_sheet.json"


@dataclass(frozen=True, slots=True)
class Estimate:
    """What the chooser believes about one tier on one kind of task."""

    p_fail: float  # verified-fail rate
    cost_micros: float  # mean cost of one attempt
    n: int  # attempts behind it (0 for a prior)
    measured: bool

    @property
    def source(self) -> str:
        return f"measured, n={self.n}" if self.measured else "prior"


# kn: unmeasured priors; replace each with the project's own rate once MIN_SAMPLE attempts exist
# Haiku: 18 of 105 blind cells failed a visible check (bench/PREREG.md E6) and a Haiku cell cost
# $0.215 on average. Sonnet and Opus: the failure rates are guesses, the costs the price ratios
# budget.py already uses (3x and 5x) applied to that cell.
PRIORS: Mapping[str, Estimate] = {
    "haiku": Estimate(0.17, 215_000, 0, False),
    "sonnet": Estimate(0.10, 645_000, 0, False),
    "opus": Estimate(0.06, 1_075_000, 0, False),
}


# --- the kind of a task -----------------------------------------------------------------------


def _bucket(n: int, edges: Sequence[tuple[int, str]], top: str) -> str:
    return next((label for limit, label in edges if n <= limit), top)


def task_kind(sheet: TermSheet, task: Task) -> str:
    """A deterministic label from the term sheet: how many files the task owns and how many checks
    verify it. Whether the task already has a failure is not in the label: it is the `retry` half
    of the statistics key (an attempt that follows a failed one), so a fresh task is judged on
    fresh attempts and the later rungs on retries."""
    paths = set(task.paths)
    files = 4 if "." in paths else len(paths)  # the whole workspace is as big as it gets
    checks = sum(c.task == task.id for c in sheet.checks)
    f = _bucket(files, ((1, "1"), (3, "2-3")), "4+")
    c = _bucket(checks, ((0, "0"), (2, "1-2"), (5, "3-5")), "6+")
    return f"files={f} checks={c}"


def features(sheet: TermSheet, task: Task) -> dict[str, int]:
    """What is known of a task before any worker runs, read from the term sheet alone, so nothing
    a benchmark knows about its own tasks (their labels, the checks it hides) can reach a start
    tier. Recorded with every start, so later runs can show which of them predicts a failure."""
    return {
        "idea_chars": len(sheet.idea),
        "tasks": len(sheet.tasks),
        "files": len(set(task.paths)),
        "checks": sum(c.task == task.id for c in sheet.checks),
    }


# --- what past runs recorded ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Attempt:
    kind: str
    retry: bool  # another worker of the same task was hired before this one
    tier: str
    failed: bool  # the gate fired it (no progress, slice limit): a verified failure
    cost_micros: int


def attempts_of(events: Sequence[Event], sheet: TermSheet) -> list[Attempt]:
    """One attempt per hired worker whose result the gate decided: delivered (every check passed)
    or fired for a reason the gate decided on evidence. A worker still running, stopped by the
    budget, blocked or disputing is no verdict; one with a slice of unknown cost has no cost."""
    kinds = {t.id: task_kind(sheet, t) for t in sheet.tasks}
    hired_before: dict[str, int] = {}
    found = []
    for hired in (e for e in events if e.event is EventType.HIRED):
        worker, task = str(hired.data.get("worker")), str(hired.data.get("task"))
        tier = tier_of(str(hired.data.get("model", "")))
        retry = hired_before.get(task, 0) > 0
        hired_before[task] = hired_before.get(task, 0) + 1
        ends = [
            e for e in events if e.event is EventType.SLICE_END and e.actor == f"worker:{worker}"
        ]
        if (
            tier is None
            or task not in kinds
            or not ends
            or any(e.cost_micros is None for e in ends)
        ):
            continue
        fired = [e for e in events if e.event is EventType.FIRED and e.data.get("worker") == worker]
        if _delivered(events, worker, len(ends)):
            failed = False
        elif any(e.data.get("reason") in ESCALATING_FIRINGS for e in fired):
            failed = True
        else:
            continue
        cost = sum(e.cost_micros or 0 for e in ends)
        found.append(Attempt(kinds[task], retry, tier, failed, cost))
    return found


@dataclass(frozen=True, slots=True)
class Stats:
    attempts: tuple[Attempt, ...] = ()

    def estimate(self, kind: str, retry: bool, tier: str) -> Estimate:
        mine = [a for a in self.attempts if (a.kind, a.retry, a.tier) == (kind, retry, tier)]
        if len(mine) < MIN_SAMPLE:
            return PRIORS[tier]
        n = len(mine)
        return Estimate(
            sum(a.failed for a in mine) / n, sum(a.cost_micros for a in mine) / n, n, True
        )

    def count(self, kind: str, retry: bool, tier: str) -> tuple[int, int, float]:
        """(attempts, verified fails, mean cost) of the data alone, whatever the sample size."""
        mine = [a for a in self.attempts if (a.kind, a.retry, a.tier) == (kind, retry, tier)]
        mean = sum(a.cost_micros for a in mine) / len(mine) if mine else 0.0
        return len(mine), sum(a.failed for a in mine), mean

    def kinds(self) -> list[str]:
        return sorted({a.kind for a in self.attempts})


@dataclass(frozen=True, slots=True)
class Collected:
    stats: Stats
    runs_read: int
    skipped: tuple[tuple[str, str], ...] = field(default=())  # (run id, why it was left out)


def _verified_attempts(root: Path) -> list[Attempt]:
    paths = RunPaths(root)
    key_file = paths.investor_key
    if key_file is None or signing.load_key(key_file) is None:
        raise ValueError("no investor key, so nothing in this run can be verified")
    events = paths.events()  # the key vouches for every investor event, the chain and the anchor
    sheet = TermSheet.from_json((root / TERM_SHEET_FILE).read_text(encoding="utf-8"))
    hashes = content_hashes(sheet, paths.checks)
    signed = (
        e
        for e in events
        if e.event is EventType.APPROVED and e.actor == "investor" and signing.SIG_KEY in e.data
    )
    if not any(e.data.get("hashes") == hashes for e in signed):
        raise ValueError("its term sheet and checks match no signed approval")
    return attempts_of(events, sheet)


def read_runs(project: Path) -> Collected:
    """Every attempt recorded by the runs of `project` that verify; the others are named, not
    read. Nothing is written."""
    runs = project / RUNS_DIR
    folders = sorted(p for p in runs.iterdir() if p.is_dir()) if runs.is_dir() else []
    attempts: list[Attempt] = []
    skipped: list[tuple[str, str]] = []
    for folder in folders:
        try:
            attempts += _verified_attempts(folder)
        except (
            LedgerError,
            signing.SigningError,
            OSError,
            ValueError,
            TypeError,
            TermSheetError,
        ) as exc:
            skipped.append(
                (folder.name, str(exc).splitlines()[0][:120] if str(exc) else type(exc).__name__)
            )
    return Collected(Stats(tuple(attempts)), len(folders) - len(skipped), tuple(skipped))


# --- the chooser ------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Choice:
    kind: str
    tier: str
    expected: Mapping[str, float]  # tier -> expected cost in micros, for each tier considered
    source: str  # where the chosen tier's own estimate came from
    why: str
    features: Mapping[str, int] = field(default_factory=dict)

    def record(self, top: str) -> dict[str, object]:
        """The start as the approval records it: the router's proposal and its reason. The sheet's
        own dispatch, which the investor may have edited, is what runs."""
        return {
            "tier": self.tier,
            "effort": rungs_from(self.tier, top)[0][1],
            "kind": self.kind,
            "source": self.source,
            "why": self.why,
            "features": dict(self.features),
        }


def expected_cost(stats: Stats, kind: str, start: str, top: str) -> float:
    """E[start] = c + p * E[next rung]; the last rung is the top tier once more at one effort step
    higher, and after it the investor is asked, which costs nothing here. The first rung is a
    fresh task; every later one follows a failure, so it uses the retry estimates.
    A rung's mean cost is its tier's (the effort step is not told apart in past runs)."""
    rungs = rungs_from(start, top)
    cost = stats.estimate(kind, len(rungs) > 1, rungs[-1][0]).cost_micros
    for i in range(len(rungs) - 2, -1, -1):
        e = stats.estimate(kind, i > 0, rungs[i][0])
        cost = e.cost_micros + e.p_fail * cost
    return cost


def choose_start(
    stats: Stats, kind: str, *, top: str, fundable: Callable[[str], bool] = lambda _t: True
) -> Choice:
    """The tier up to `top` that the round can fund and whose ladder has the least expected cost;
    the cheaper tier on a tie. `fundable` is the round's own test (`dispatch.fits`)."""
    options = [t for t in TIERS[: rank(top) + 1] if fundable(t)] or [TIERS[0]]
    expected = {t: expected_cost(stats, kind, t, top) for t in options}
    tier = min(options, key=lambda t: (expected[t], rank(t)))
    est = stats.estimate(kind, False, tier)
    others = ", ".join(f"{t} ${expected[t] / 1e6:.3f}" for t in options if t != tier)
    why = f"lowest expected cost ${expected[tier] / 1e6:.3f}" + (
        f" (vs {others})" if others else ""
    )
    if not est.measured:
        why = f"cold start, under {MIN_SAMPLE} verified attempts of this kind on {tier}: {why}"
    return Choice(kind, tier, expected, est.source, why)


# --- the view ---------------------------------------------------------------------------------


def _row(cells: Iterable[str], widths: Sequence[int]) -> str:
    return "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)).rstrip()


def render_routing(collected: Collected, *, top: str) -> list[str]:
    """Per task kind and tier: attempts, fail rate, mean cost, the start tier chosen and why."""
    stats = collected.stats
    lines = [
        "ROUTING (start tier per task kind, from this project's verified past runs)",
        f"Runs read: {collected.runs_read}; left out: {len(collected.skipped)}"
        + "".join(f"\n  {run}: {why}" for run, why in collected.skipped),
        f"Attempts with a verdict: {len(stats.attempts)}. Below {MIN_SAMPLE} attempts of a kind "
        "and tier the prior is used and marked so.",
        "",
    ]
    rows = [("kind", "after", "tier", "attempts", "fail rate", "mean cost", "used")]
    kinds = stats.kinds()
    for kind in kinds:
        for retry in (False, True):
            for tier in TIERS:
                n, fails, mean = stats.count(kind, retry, tier)
                if not n:
                    continue
                used = stats.estimate(kind, retry, tier)
                rows.append(
                    (
                        kind,
                        "a failure" if retry else "fresh",
                        tier,
                        str(n),
                        f"{fails / n:.0%}",
                        f"${mean / 1e6:.3f}",
                        f"{used.source} (fail {used.p_fail:.0%}, ${used.cost_micros / 1e6:.3f})",
                    )
                )
    if len(rows) == 1:
        lines.append("No recorded attempts: every kind starts from the priors below.")
    else:
        widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
        lines += [_row(r, widths) for r in rows]
    lines += ["", "Priors (used below the sample minimum):"]
    lines += [
        f"  {t}: fail {PRIORS[t].p_fail:.0%}, ${PRIORS[t].cost_micros / 1e6:.3f} an attempt"
        for t in TIERS
    ]
    lines += ["", f"Chosen start tier (ladder up to {top}: {_ladder_text(top)})"]
    chosen = [_row(("kind", "start", "from", "why"), (24, 6, 20, 0))]
    for kind in kinds or ["files=1 checks=1-2"]:
        c = choose_start(stats, kind, top=top)
        chosen.append(_row((kind, c.tier, c.source, c.why), (24, 6, 20, 0)))
    return lines + chosen


def _ladder_text(top: str) -> str:
    return " > ".join(t if e == "off" else f"{t}/{e}" for t, e in ladder(top))


def starts_for(
    sheet: TermSheet, stats: Stats, *, top: str, fundable: Callable[[str], bool]
) -> dict[str, Choice]:
    """The chosen start of every task of the sheet."""
    return {
        t.id: replace(
            choose_start(stats, task_kind(sheet, t), top=top, fundable=fundable),
            features=features(sheet, t),
        )
        for t in sheet.tasks
    }
