"""Offline evaluation of `boss.spec`: no model call, nothing spent.

Reads the benchmark ideas, hand labels (`bench/spec_truth/`) and saved boss drafts and mutants,
and reports five measurements against criteria that were committed before the first run
(`bench/spec_truth/CRITERIA.md`; the header of every report names that file's hash, and a test pins
the numbers below to it):

O1  the splitter's properties on every idea and on its numbering-stripped copy
O2  how well a lexical proposer agrees with the hand labels (hidden check -> rules)
O3  recall of the free verifier on the known omissions, and how many rules it flags per draft
O4  whether "an anchor of the rule is in the draft" predicts a mutant violating it is killed
O5  how often a flag is on a rule that no saved product ever failed

Run: `python -m boss.bench.spec_eval all --raw bench/results/raw --out report.md`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from boss import spec
from boss.bench.score import draft_checks
from boss.bench.tasks import MUTANT_TIMEOUT_S, BenchTask, load_tasks
from boss.gate import Check, CheckResult, CheckStatus, run_gate
from boss.stats import wilson_interval

# Fixed before the first run; `tests/test_bench_spec_eval.py` pins them to CRITERIA.md.
MAX_SENTENCES = 40
SENTENCE_SHARE = 0.95  # of ideas with at most MAX_SENTENCES sentences
RECALL = 0.60  # of known-omission cells with a flagged rule that is their failing behaviour
BURDEN_MEDIAN = 4  # flagged rules per draft, at most
GAP_POINTS = 25  # kill rate (all anchors present) minus kill rate (an anchor missing)
MIN_TRIPLES = 40  # per side
AGREEMENT = 0.70  # proposer top-1 against the hand labels
KNOWN_OMISSIONS = 15
RETRY_TIMEOUT_S = 120.0
EXCLUDED_CELLS = frozenset({("wildcard", 1)})  # class (b): a wrong boss check, not an omission
DRAFT_GROUPS = ("final3", "heldout3", "pilot", "rerun1", "drafts-single", "drafts-single-think0")
PRODUCT_GROUPS = ("final3", "heldout3", "pilot", "rerun1")
# The populations are named, never found by listing the label files: a label file that lands later
# must not change what CRITERIA.md measured. The scored set is the 17 original tasks; the held-out
# set is the 18 later tasks, run apart and never pooled with it.
SCORED_TASKS = (
    "bigdecimal",
    "calc",
    "csvline",
    "duration",
    "intervals",
    "jsonpointer",
    "justify",
    "linediff",
    "lrucache",
    "matrixops",
    "roman",
    "semver",
    "slugify",
    "tokenbucket",
    "toposort",
    "wildcard",
    "workdays",
)
HELD_OUT_TASKS = (
    "bytesize",
    "cronnext",
    "dedentblock",
    "exprtokens",
    "fracmath",
    "iniparse",
    "isoweek",
    "luhn",
    "mdheadings",
    "minheap",
    "moneysplit",
    "prefixtrie",
    "rangesum",
    "ringbuffer",
    "shortestpath",
    "unionfind",
    "urlquery",
    "wordwrap",
)
HELD_OUT_GROUPS = ("new18",)
POPULATIONS = ("scored", "held-out")
HARVESTED = re.compile(r"(?:pilot|rerun|final|heldout)")
STEPS = ("o1", "o2", "o3", "o4", "o5")
EXTRA_STEPS = ("o4b",)  # added after the first run; not part of "all" and has no criterion
CRITERIA_FILE = "CRITERIA.md"


class EvalError(Exception):
    """An input is missing or does not match what the labels were made for."""


# --- labels (O2's ground truth) --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Labels:
    task: str
    split: spec.Split
    hidden: dict[str, tuple[str, ...]]  # hidden check name -> the rules it tests

    def rules_of(self, checks: Sequence[str]) -> set[str]:
        return {r for c in checks for r in self.hidden.get(c, ())}

    def checks_of(self, rule: str) -> tuple[str, ...]:
        return tuple(c for c, rules in self.hidden.items() if rule in rules)


def load_labels(truth_dir: Path, task: BenchTask) -> Labels:
    """The hand labels of one task, accepted only for the idea and splitter they were made for."""
    path = truth_dir / f"{task.id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvalError(f"cannot read the labels {path.name}: {exc}") from exc
    split = spec.split(task.idea)
    if raw.get("idea_sha256") != split.idea_sha256 or raw.get("splitter") != spec.SPLITTER:
        raise EvalError(f"{path.name} was made for another idea or splitter; relabel the task")
    by_id = split.by_id()
    for rule_id, prefix in raw.get("rules", {}).items():
        rule = by_id.get(rule_id)
        if rule is None or " ".join(rule.text.split())[:60] != prefix:
            raise EvalError(f"{path.name}: rule {rule_id} is not the rule that was labelled")
    hidden = {name: tuple(rules) for name, rules in raw.get("hidden", {}).items()}
    names = {c.id for c in task.hidden_checks()}
    if set(hidden) != names:
        raise EvalError(
            f"{path.name}: labels cover {sorted(hidden)}, hidden checks are {sorted(names)}"
        )
    for name, rules in hidden.items():
        if not rules or any(r not in by_id for r in rules):
            raise EvalError(f"{path.name}: {name} names no rule or an unknown one")
    return Labels(task.id, split, hidden)


# --- O1: the splitter -------------------------------------------------------------------------

_NUMBERED = re.compile(r"^[ \t]{0,3}(\d{1,3})[.)][ \t]+", re.M)


def split_problems(idea: str) -> list[str]:
    """Every property the splitter must have for `idea`, as one line each when it fails."""
    problems: list[str] = []
    try:
        first = spec.split(idea)
    except spec.SpecError as exc:
        return [f"refused: {exc}"]
    if first != spec.split(idea):
        problems.append("not deterministic")
    end = 0
    for n, rule in enumerate(first.rules, start=1):
        if rule.id != f"R{n:02d}":
            problems.append(f"{rule.id} is out of sequence")
        if rule.text != idea[rule.start : rule.end]:
            problems.append(f"{rule.id}: offsets do not reproduce the text")
        if not any(c.isalpha() for c in rule.text) or rule.text != rule.text.strip():
            problems.append(f"{rule.id}: empty or untrimmed")
        if rule.start < end:
            problems.append(f"{rule.id}: overlaps the rule before it")
        end = rule.end
    wanted = {f"G{m[1]}" for m in _NUMBERED.finditer(idea)}
    if wanted and not wanted <= {r.group for r in first.rules}:
        problems.append(f"no rule for items {sorted(wanted - {r.group for r in first.rules})}")
    return problems


def strip_numbering(idea: str) -> str:
    """The same sentences as plain prose: no list markers, one line a paragraph."""
    lines = [_NUMBERED.sub("", line) for line in idea.split("\n")]
    return "\n".join(" ".join(p.split()) for p in "\n".join(lines).split("\n\n"))


def sentence_count(idea: str) -> int:
    """Sentences before the cap that turns a long idea into one rule per group."""
    blocks, _, _ = spec._blocks(idea)
    return sum(len(spec._sentences(idea, a, b)) for a, b, _ in blocks)


@dataclass(frozen=True, slots=True)
class O1:
    ideas: int
    failures: dict[str, list[str]]  # idea or "<idea> (stripped)" -> problems
    within_cap: int
    coarse: tuple[str, ...]
    rules: tuple[int, ...]
    scored: tuple[int, ...]
    stripped_rules: tuple[int, ...]

    @property
    def passed(self) -> bool:
        return not self.failures and self.within_cap / self.ideas >= SENTENCE_SHARE


def run_o1(tasks: Sequence[BenchTask]) -> O1:
    failures: dict[str, list[str]] = {}
    within, coarse, rules, scored, stripped = 0, [], [], [], []
    for task in tasks:
        idea = task.idea
        for label, text in ((task.id, idea), (f"{task.id} (stripped)", strip_numbering(idea))):
            if problems := split_problems(text):
                failures[label] = problems
        within += sentence_count(idea) <= MAX_SENTENCES
        split = spec.split(idea)
        if split.coarse:
            coarse.append(task.id)
        rules.append(len(split.rules))
        scored.append(len(split.scorable))
        stripped.append(len(spec.split(strip_numbering(idea)).rules))
    return O1(
        len(tasks), failures, within, tuple(coarse), tuple(rules), tuple(scored), tuple(stripped)
    )


# --- O2: the lexical proposer -----------------------------------------------------------------

_STOP_TEXT = (
    "the and for with that this are not any its has have into from when then than only also "
    "each every one two all can may must never always whose which what where there their them they"
)
_STOP = frozenset(_STOP_TEXT.split())
_WORDS = re.compile(r"[a-z]{3,}")


def _words(text: str) -> set[str]:
    return {w for w in _WORDS.findall(text.lower().replace("_", " ")) if w not in _STOP}


def propose(task: BenchTask, split: spec.Split) -> dict[str, str]:
    """For each hidden check, the one scored rule it most resembles: word overlap between the
    rule and the check's file name, test names and string constants, plus a bonus for each anchor
    of the rule the check contains. A starting point for a person, never a label."""
    best: dict[str, str] = {}
    for check in task.hidden_checks():
        source = (task.hidden_dir / check.file).read_text(encoding="utf-8")
        found = spec.facts(source)
        names = check.id + " " + " ".join(re.findall(r"def (test_\w+)", source))
        pool = _words(names) | _words(" ".join(found.strings if found else ()))
        scored = 0.0
        pick = ""
        for rule in split.scorable:
            words = _words(rule.text)
            score = len(words & pool) / (len(words) ** 0.5 or 1)
            if found:
                score += 2 * sum(1 for a in rule.anchors if spec.present(a, [found]))
            if score > scored:
                scored, pick = score, rule.id
        best[check.id] = pick
    return best


def agreement(labels: Labels, proposed: Mapping[str, str]) -> tuple[int, int]:
    hits = sum(1 for check, rule in proposed.items() if rule in labels.hidden.get(check, ()))
    return hits, len(proposed)


# --- saved drafts and cells -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DraftRef:
    group: str
    task: str
    rep: int
    checks_dir: Path

    @property
    def key(self) -> str:
        return f"{self.group}/{self.task}/rep{self.rep}/{self.checks_dir.parent.name}"


def find_drafts(raw: Path, tasks: set[str], groups: Sequence[str] = DRAFT_GROUPS) -> list[DraftRef]:
    """Every saved draft of these tasks: a folder `checks` with test_*.py in it."""
    found = []
    for group in groups:
        base = raw / group
        if not base.is_dir():
            continue
        for checks_dir in sorted(base.rglob("checks")):
            parts = checks_dir.relative_to(base).parts
            if parts[0] not in tasks or not any(checks_dir.glob("test_*.py")):
                continue
            rep = next((int(m[1]) for p in parts if (m := re.fullmatch(r"rep(\d+)", p))), 0)
            found.append(DraftRef(group, parts[0], rep, checks_dir))
    return found


def read_sources(checks_dir: Path) -> dict[str, str]:
    """The check files as the boss names them: test_c01.py is check c01."""
    return {
        p.name.removesuffix(".py").removeprefix("test_"): p.read_text(
            encoding="utf-8", errors="replace"
        )
        for p in sorted(checks_dir.glob("test_*.py"))
    }


@dataclass(frozen=True, slots=True)
class Cell:
    task: str
    rep: int
    failed: tuple[str, ...]  # hidden checks that did not pass
    checks_dir: Path


def known_omissions(raw: Path) -> list[Cell]:
    """The firm cells of `final3` that failed a hidden check, except the class (b) cell."""
    cells = []
    for result in sorted((raw / "final3").glob("*/firm/rep*/result.json")):
        data = json.loads(result.read_text(encoding="utf-8"))
        hidden = data.get("hidden")
        if not isinstance(hidden, dict):
            continue
        failed = tuple(sorted(k for k, v in hidden.items() if v != "passed"))
        task, rep = result.parts[-4], int(result.parts[-2].removeprefix("rep"))
        if failed and (task, rep) not in EXCLUDED_CELLS:
            runs = sorted((result.parent / ".boss" / "runs").glob("*/checks"))
            if len(runs) != 1:
                raise EvalError(f"{result.parent}: expected one run folder, found {len(runs)}")
            cells.append(Cell(task, rep, failed, runs[0]))
    if len(cells) != KNOWN_OMISSIONS:
        raise EvalError(f"expected {KNOWN_OMISSIONS} known omissions in final3, found {len(cells)}")
    return cells


def product_failures(
    raw: Path, task: str, groups: Sequence[str] = PRODUCT_GROUPS
) -> list[set[str]]:
    """For each saved product of the task, the hidden checks it did not pass."""
    out = []
    for group in groups:
        for result in sorted((raw / group).glob(f"{task}/*/rep*/result.json")):
            hidden = json.loads(result.read_text(encoding="utf-8")).get("hidden")
            if isinstance(hidden, dict):
                out.append({k for k, v in hidden.items() if v != "passed"})
    return out


# --- O3: the free verifier on the known omissions ---------------------------------------------


@dataclass(frozen=True, slots=True)
class O3Cell:
    cell: Cell
    flagged: tuple[str, ...]
    hit: tuple[str, ...]  # flagged rules that are rules of a failing hidden check
    types: tuple[str, ...]  # anchor types that were missing on the hits
    scorable: int = 0  # scored rules of the idea
    failing: int = 0  # scored rules of the cell's failing hidden checks

    @property
    def chance(self) -> float:
        """The probability that as many flags, drawn at random from the scored rules, would hit."""
        k = len(self.flagged)
        if not self.scorable or k > self.scorable:
            return 1.0
        return 1 - math.comb(self.scorable - self.failing, k) / math.comb(self.scorable, k)


@dataclass(frozen=True, slots=True)
class O3:
    cells: tuple[O3Cell, ...]
    flags_per_draft: tuple[int, ...]
    by_group: dict[str, tuple[int, ...]]
    flagged: dict[str, dict[str, tuple[str, ...]]]  # draft key -> flagged rule -> missing types
    by_type: dict[str, tuple[int, int]]  # missing anchor type -> (flags that are hits, flags)
    base: tuple[int, int]  # scored rules of the failing checks, scored rules, over the cells

    @property
    def recall(self) -> float:
        return sum(1 for c in self.cells if c.hit) / len(self.cells) if self.cells else 0.0

    @property
    def median_burden(self) -> float:
        return statistics.median(self.flags_per_draft)

    @property
    def recall_passed(self) -> bool:
        return self.recall >= RECALL

    @property
    def burden_passed(self) -> bool:
        return self.median_burden <= BURDEN_MEDIAN


def run_o3(drafts: Sequence[DraftRef], labels: Mapping[str, Labels], cells: Sequence[Cell]) -> O3:
    flags: dict[str, tuple[str, dict[str, tuple[str, ...]]]] = {}
    for ref in drafts:
        gaps = spec.draft_gaps(labels[ref.task].split, read_sources(ref.checks_dir))
        flags[ref.key] = (ref.group, {r: tuple(a.type for a in lost) for r, lost in gaps.items()})
    by_group: dict[str, list[int]] = defaultdict(list)
    for group, found in flags.values():
        by_group[group].append(len(found))
    rows = []
    typed: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    base = [0, 0]
    for cell in cells:
        gaps = spec.draft_gaps(labels[cell.task].split, read_sources(cell.checks_dir))
        truth = labels[cell.task].rules_of(cell.failed)
        hit = tuple(r for r in gaps if r in truth)
        for rule, lost in gaps.items():
            for kind in {a.type for a in lost}:
                typed[kind][0] += rule in truth
                typed[kind][1] += 1
        scored_ids = {r.id for r in labels[cell.task].split.scorable}
        base[0] += len(truth & scored_ids)
        base[1] += len(scored_ids)
        scorable = {r.id for r in labels[cell.task].split.scorable}
        rows.append(
            O3Cell(
                cell,
                tuple(gaps),
                hit,
                tuple(sorted({a.type for r in hit for a in gaps[r]})),
                len(scorable),
                len(truth & scorable),
            )
        )
    return O3(
        tuple(rows),
        tuple(len(found) for _, found in flags.values()),
        {g: tuple(v) for g, v in sorted(by_group.items())},
        {key: found for key, (_, found) in flags.items()},
        {k: (v[0], v[1]) for k, v in sorted(typed.items())},
        (base[0], base[1]),
    )


# --- O4: does an anchor predict a kill? -------------------------------------------------------


def hand_mutants(task: BenchTask) -> list[Path]:
    return [m for m in task.mutants() if not HARVESTED.match(m.name)]


def gate(
    workspace: Path, checks_dir: Path, checks: Sequence[Check], timeout_s: float
) -> list[CheckResult]:
    """`run_gate`, with each check that timed out run once more under a longer limit: on a busy
    machine a slow check is not a hang, and one that still hangs under the longer limit is."""
    results = run_gate(workspace, checks_dir, checks, timeout_s=timeout_s)
    slow = [
        c
        for c in checks
        if any(r.check_id == c.id and r.status is CheckStatus.TIMEOUT for r in results)
    ]
    if not slow:
        return results
    again = {
        r.check_id: r for r in run_gate(workspace, checks_dir, slow, timeout_s=RETRY_TIMEOUT_S)
    }
    return [again.get(r.check_id, r) for r in results]


def mutant_violations(task: BenchTask, labels: Labels) -> dict[str, set[str]]:
    """For each hand mutant, the rules of the hidden checks it fails."""
    out = {}
    for mutant in hand_mutants(task):
        results = gate(mutant, task.hidden_dir, task.hidden_checks(), MUTANT_TIMEOUT_S)
        out[mutant.name] = labels.rules_of([r.check_id for r in results if not r.passed])
    return out


def kills(task: BenchTask, checks_dir: Path) -> dict[str, bool]:
    """Whether the draft kills each hand mutant: a sound check (one the reference passes) fails."""
    checks = draft_checks(checks_dir)
    wrong = {r.check_id for r in gate(task.reference_dir, checks_dir, checks, 60.0) if not r.passed}
    out = {}
    for mutant in hand_mutants(task):
        failed = {
            r.check_id for r in gate(mutant, checks_dir, checks, MUTANT_TIMEOUT_S) if not r.passed
        }
        out[mutant.name] = bool(failed - wrong)
    return out


@dataclass(frozen=True, slots=True)
class Side:
    killed: int
    total: int

    @property
    def rate(self) -> float:
        return self.killed / self.total if self.total else 0.0


@dataclass(frozen=True, slots=True)
class O4:
    present: Side  # every anchor of the rule is in the draft
    missing: Side  # at least one anchor is not
    by_missing_type: dict[str, Side]
    drafts: int
    mutants: int

    @property
    def gap(self) -> float:
        return (self.present.rate - self.missing.rate) * 100

    @property
    def enough(self) -> bool:
        return min(self.present.total, self.missing.total) >= MIN_TRIPLES

    @property
    def passed(self) -> bool:
        return self.enough and self.gap >= GAP_POINTS


def run_o4(
    drafts: Sequence[DraftRef],
    tasks: Mapping[str, BenchTask],
    labels: Mapping[str, Labels],
    kill_map: Mapping[str, Mapping[str, bool]],
    violations: Mapping[str, Mapping[str, set[str]]],
) -> O4:
    present = [0, 0]
    missing = [0, 0]
    typed: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    used = 0
    for ref in drafts:
        killed = kill_map.get(ref.key)
        if killed is None:
            continue
        used += 1
        split = labels[ref.task].split
        gaps = spec.draft_gaps(split, read_sources(ref.checks_dir))
        for rule in split.scorable:
            if not rule.anchors:
                continue
            for mutant, rules in violations[ref.task].items():
                if rule.id not in rules or mutant not in killed:
                    continue
                if rule.id in gaps:
                    side = missing
                    for kind in {a.type for a in gaps[rule.id]}:
                        typed[kind][0] += killed[mutant]
                        typed[kind][1] += 1
                else:
                    side = present
                side[0] += killed[mutant]
                side[1] += 1
    return O4(
        Side(*present),
        Side(*missing),
        {k: Side(*v) for k, v in sorted(typed.items())},
        used,
        sum(len(v) for v in violations.values()),
    )


# --- O4b: failing products as the mutants (added after the first run) --------------------------


@dataclass(frozen=True, slots=True)
class Product:
    group: str
    task: str
    arm: str
    rep: int
    path: Path
    failed: str  # the one hidden check it failed

    @property
    def key(self) -> str:
        return f"{self.group}/{self.task}/{self.arm}/rep{self.rep}"

    def built_from(self, draft: DraftRef) -> bool:
        """The firm product that was built against this very draft."""
        return self.arm == "firm" and (draft.group, draft.task, draft.rep) == (
            self.group,
            self.task,
            self.rep,
        )


def failing_products(
    raw: Path, tasks: set[str], groups: Sequence[str] = PRODUCT_GROUPS
) -> list[Product]:
    """Saved products that failed exactly one hidden check: real wrong implementations, each with
    one behaviour to blame, from the four groups that ran products."""
    found = []
    for group in groups:
        for result in sorted((raw / group).glob("*/*/rep*/result.json")):
            task, arm, rep = result.parts[-4], result.parts[-3], int(result.parts[-2][3:])
            hidden = json.loads(result.read_text(encoding="utf-8")).get("hidden")
            if task not in tasks or not isinstance(hidden, dict):
                continue
            failed = [k for k, v in hidden.items() if v != "passed"]
            if len(failed) != 1:
                continue
            runs = sorted((result.parent / ".boss" / "runs").glob("*/product"))
            path = result.parent / "workspace" if arm == "single" else (runs[0] if runs else None)
            if path is not None and path.is_dir() and any(path.iterdir()):
                found.append(Product(group, task, arm, rep, path, failed[0]))
    return found


def kills_products(
    task: BenchTask, checks_dir: Path, products: Sequence[Product]
) -> dict[str, bool]:
    """Whether the draft kills each product: a sound check (one the reference passes) fails."""
    checks = draft_checks(checks_dir)
    wrong = {r.check_id for r in gate(task.reference_dir, checks_dir, checks, 60.0) if not r.passed}
    out = {}
    for product in products:
        failed = {
            r.check_id
            for r in gate(product.path, checks_dir, checks, MUTANT_TIMEOUT_S)
            if not r.passed
        }
        out[product.key] = bool(failed - wrong)
    return out


def run_o4b(
    drafts: Sequence[DraftRef],
    labels: Mapping[str, Labels],
    products: Sequence[Product],
    kill_map: Mapping[str, Mapping[str, bool]],
) -> O4:
    present = [0, 0]
    missing = [0, 0]
    typed: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    used = 0
    for ref in drafts:
        killed = kill_map.get(ref.key)
        if killed is None:
            continue
        used += 1
        split = labels[ref.task].split
        gaps = spec.draft_gaps(split, read_sources(ref.checks_dir))
        for product in products:
            if product.task != ref.task or product.built_from(ref) or product.key not in killed:
                continue
            blamed = labels[ref.task].rules_of([product.failed])
            for rule in split.scorable:
                if not rule.anchors or rule.id not in blamed:
                    continue
                if rule.id in gaps:
                    side = missing
                    for kind in {a.type for a in gaps[rule.id]}:
                        typed[kind][0] += killed[product.key]
                        typed[kind][1] += 1
                else:
                    side = present
                side[0] += killed[product.key]
                side[1] += 1
    return O4(
        Side(*present),
        Side(*missing),
        {k: Side(*v) for k, v in sorted(typed.items())},
        used,
        len(products),
    )


# --- O5: noise --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class O5:
    flags: int
    harmless: int  # on a rule whose hidden checks every saved product of the task passed
    unlabelled: int  # on a rule no hidden check was labelled with


def run_o5(o3: O3, labels: Mapping[str, Labels], failures: Mapping[str, Sequence[set[str]]]) -> O5:
    flags = harmless = unlabelled = 0
    for key, found in o3.flagged.items():
        task = key.split("/")[1]
        for rule in found:
            flags += 1
            checks = labels[task].checks_of(rule)
            if not checks:
                unlabelled += 1
            elif not any(set(checks) & failed for failed in failures[task]):
                harmless += 1
    return O5(flags, harmless, unlabelled)


# --- running and reporting --------------------------------------------------------------------


def criteria_header(truth_dir: Path, population: str = "scored") -> str:
    try:
        sha = hashlib.sha256((truth_dir / CRITERIA_FILE).read_bytes()).hexdigest()[:16]
    except OSError:
        sha = "missing"
    if population == "held-out":
        return "\n".join(
            [
                "# Offline evaluation of the spec layer: HELD-OUT population (the 18 later tasks)",
                "",
                f"`SPLITTER` {spec.SPLITTER}. No criterion was fixed for this population: its "
                "numbers are read against the scored run's (`CRITERIA.md`), never pooled.",
            ]
        )
    return "\n".join(
        [
            "# Offline evaluation of the spec layer",
            "",
            f"Criteria fixed before the run (`{CRITERIA_FILE}`, sha256 {sha}) and `SPLITTER` "
            f"{spec.SPLITTER}:",
            f"- O1 pass: all properties hold on every idea and its stripped copy; at most "
            f"{MAX_SENTENCES} sentences in at least {SENTENCE_SHARE:.0%} of ideas",
            f"- O2: proposer top-1 agreement at least {AGREEMENT:.0%}, else hand labels only",
            f"- O3 recall pass: at least {RECALL:.0%} of the {KNOWN_OMISSIONS} known-omission "
            "cells have a flagged rule that is their failing behaviour",
            f"- O3 burden pass: median flags per draft at most {BURDEN_MEDIAN}",
            f"- O4 pass: kill-rate gap at least {GAP_POINTS} points, with at least {MIN_TRIPLES} "
            "triples on each side",
            "- O5: reported only",
        ]
    )


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _interval(side: Side) -> str:
    low, high = wilson_interval(side.killed, side.total)
    return f"{side.killed}/{side.total} = {_pct(side.rate)} [{_pct(low)}-{_pct(high)}]"


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def render_o1(o1: O1) -> str:
    med = statistics.median
    lines = [
        "## O1 the splitter",
        "",
        f"- {o1.ideas} ideas; property failures: {len(o1.failures)}; sentences <= "
        f"{MAX_SENTENCES} in {o1.within_cap}/{o1.ideas} ({o1.within_cap / o1.ideas:.1%}): "
        f"**{_verdict(o1.passed)}**",
        f"- rules per idea: min {min(o1.rules)}, median {med(o1.rules)}, max {max(o1.rules)}; "
        f"scored median {med(o1.scored)}; coarse (one rule per group): "
        f"{', '.join(o1.coarse) or 'none'}",
        f"- numbering stripped: median rules {med(o1.stripped_rules)} against {med(o1.rules)} "
        "(reported, not gated)",
    ]
    lines += [f"  - {k}: {'; '.join(v[:3])}" for k, v in sorted(o1.failures.items())]
    return "\n".join(lines)


def render_o2(rows: Sequence[tuple[str, int, int]]) -> str:
    hits, total = sum(r[1] for r in rows), sum(r[2] for r in rows)
    share = hits / total if total else 0.0
    lines = [
        "## O2 the lexical proposer against the hand labels",
        "",
        f"- top-1 agreement {hits}/{total} = {_pct(share)} (criterion {AGREEMENT:.0%}): "
        f"{'proposer usable as a starting point' if share >= AGREEMENT else 'hand labels only'}",
    ]
    lines += [f"  - {t}: {h}/{n}" for t, h, n in rows]
    return "\n".join(lines)


def render_o3(o3: O3) -> str:
    n = len(o3.cells)
    hits = sum(1 for c in o3.cells if c.hit)
    lines = [
        "## O3 the free verifier on the known omissions",
        "",
        f"- recall {hits}/{n} = {_pct(o3.recall)} (criterion {RECALL:.0%}): "
        f"**{_verdict(o3.recall_passed)}**",
        f"- burden: median {o3.median_burden:g} flagged rules per draft over "
        f"{len(o3.flags_per_draft)} drafts (criterion <= {BURDEN_MEDIAN}): "
        f"**{_verdict(o3.burden_passed)}**",
        "- chance baseline (added after the first run, not a criterion): flagging the same number "
        f"of rules at random would hit {sum(c.chance for c in o3.cells):.1f} of {n} cells; the "
        f"cells' own flag counts have median "
        f"{statistics.median(len(c.flagged) for c in o3.cells):g}",
        "",
        "| cell | failing hidden checks | flagged | hit | missing anchor types |",
        "|---|---|---|---|---|",
    ]
    for c in o3.cells:
        lines.append(
            f"| {c.cell.task} rep{c.cell.rep} | {', '.join(c.cell.failed)} | "
            f"{', '.join(c.flagged)} | {', '.join(c.hit) or '-'} | {', '.join(c.types) or '-'} |"
        )
    lines += [
        "",
        "Precision of a flag by the type of the missing anchor, in these cells (added after the "
        "first run; a flag is right when its rule is a rule of a failing hidden check). "
        f"Base rate: {o3.base[0]}/{o3.base[1]} = {_pct(o3.base[0] / o3.base[1])} of scored rules "
        "are such rules.",
        "",
        "| missing anchor | right / flags |",
        "|---|---|",
    ]
    lines += [f"| {k} | {h}/{n} = {_pct(h / n)} |" for k, (h, n) in o3.by_type.items()]
    lines += ["", "Flags per draft by group (median, drafts):"]
    lines += [f"- {g}: {statistics.median(v):g}, {len(v)}" for g, v in o3.by_group.items()]
    return "\n".join(lines)


def render_o3_burden(o3: O3) -> str:
    """The held-out population has no known-omission cells (that list belongs to the scored set),
    so only the length of the flag list is measured."""
    lines = [
        "## O3 burden (held-out population; recall is not measured: no known omissions here)",
        "",
        f"- median {o3.median_burden:g} flagged rules per draft over {len(o3.flags_per_draft)} "
        f"drafts (the scored set's criterion was <= {BURDEN_MEDIAN})",
        "",
        "Flags per draft by group (median, drafts):",
    ]
    lines += [f"- {g}: {statistics.median(v):g}, {len(v)}" for g, v in o3.by_group.items()]
    return "\n".join(lines)


def render_o4(o4: O4) -> str:
    state = _verdict(o4.passed) if o4.enough else "INCONCLUSIVE (too few triples on a side)"
    lines = [
        "## O4 does an anchor predict a kill?",
        "",
        f"- drafts scored {o4.drafts}; hand mutants in play {o4.mutants}",
        f"- all anchors present: {_interval(o4.present)}",
        f"- an anchor missing: {_interval(o4.missing)}",
        f"- gap {o4.gap:.1f} points (criterion >= {GAP_POINTS}, >= {MIN_TRIPLES} per side): "
        f"**{state}**",
    ]
    if o4.by_missing_type:
        lines += ["", "Kill rate when a rule has a missing anchor of this type:"]
        lines += [f"- {k}: {_interval(v)}" for k, v in o4.by_missing_type.items()]
    return "\n".join(lines)


def render_o5(o5: O5) -> str:
    share = o5.harmless / o5.flags if o5.flags else 0.0
    return "\n".join(
        [
            "## O5 noise (reported only)",
            "",
            f"- {o5.flags} flags over all drafts; {o5.harmless} ({_pct(share)}) on a rule whose "
            f"hidden checks every saved product of the task passed; {o5.unlabelled} on a rule no "
            "hidden check was labelled with",
        ]
    )


def run(
    steps: Sequence[str],
    *,
    tasks_dir: Path,
    truth_dir: Path,
    raw: Path | None,
    workers: int = 8,
    cache_path: Path | None = None,
    population: str = "scored",
) -> str:
    """The whole report for the chosen steps, for one named population.

    `scored` is the 17 tasks CRITERIA.md fixed; `held-out` is the 18 later ones, which are never
    pooled with them. Which tasks are in a population is the lists above, not the label files
    that happen to exist.
    """
    if population not in POPULATIONS:
        raise EvalError(f"population must be one of {POPULATIONS}, got {population!r}")
    held_out = population == "held-out"
    named = HELD_OUT_TASKS if held_out else SCORED_TASKS
    all_tasks = load_tasks(tasks_dir)
    known = {t.id: t for t in all_tasks}
    if missing_tasks := [t for t in named if t not in known]:
        raise EvalError(
            f"tasks named for the {population} population are not in {tasks_dir}: {missing_tasks}"
        )
    chosen = [known[t] for t in named]
    labels = {t.id: load_labels(truth_dir, t) for t in chosen}
    by_id = {t.id: t for t in chosen}
    parts = [criteria_header(truth_dir, population)]
    if "o1" in steps:
        parts.append(render_o1(run_o1(chosen if held_out else all_tasks)))
    if "o2" in steps:
        parts.append(
            render_o2(
                [
                    (t, *agreement(labels[t], propose(by_id[t], labels[t].split)))
                    for t in sorted(labels)
                ]
            )
        )
    needs_raw = [s for s in steps if s in ("o3", "o4", "o4b", "o5")]
    if needs_raw and raw is None:
        raise EvalError("O3-O5 need --raw, the folder of saved cells")
    if raw is not None and needs_raw:
        draft_groups = HELD_OUT_GROUPS if held_out else DRAFT_GROUPS
        product_groups = HELD_OUT_GROUPS if held_out else PRODUCT_GROUPS
        drafts = find_drafts(raw, set(labels), draft_groups)
        o3 = run_o3(drafts, labels, [] if held_out else known_omissions(raw))
        if "o3" in steps:
            parts.append(render_o3_burden(o3) if held_out else render_o3(o3))
        if "o4" in steps:
            parts.append(render_o4(_o4(drafts, by_id, labels, workers, cache_path)))
        if "o4b" in steps:
            parts.append(_o4b(drafts, raw, by_id, labels, workers, cache_path, product_groups))
        if "o5" in steps:
            failures = {t: product_failures(raw, t, product_groups) for t in labels}
            parts.append(render_o5(run_o5(o3, labels, failures)))
    return "\n\n".join(parts) + "\n"


def _o4(
    drafts: Sequence[DraftRef],
    tasks: Mapping[str, BenchTask],
    labels: Mapping[str, Labels],
    workers: int,
    cache_path: Path | None,
) -> O4:
    cache: dict[str, dict[str, bool]] = {}
    if cache_path is not None and cache_path.is_file():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    todo = [d for d in drafts if d.key not in cache]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ref, result in zip(
            todo, pool.map(lambda d: kills(tasks[d.task], d.checks_dir), todo), strict=True
        ):
            cache[ref.key] = result
    if cache_path is not None:
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    violations = {t: mutant_violations(tasks[t], labels[t]) for t in labels}
    return run_o4(drafts, tasks, labels, cache, violations)


def _o4b(
    drafts: Sequence[DraftRef],
    raw: Path,
    tasks: Mapping[str, BenchTask],
    labels: Mapping[str, Labels],
    workers: int,
    cache_path: Path | None,
    groups: Sequence[str] = PRODUCT_GROUPS,
) -> str:
    products = failing_products(raw, set(labels), groups)
    path = cache_path.with_name(cache_path.stem + "-o4b.json") if cache_path else None
    cache: dict[str, dict[str, bool]] = {}
    if path is not None and path.is_file():
        cache = json.loads(path.read_text(encoding="utf-8"))

    def work(ref: DraftRef) -> dict[str, bool]:
        mine = [p for p in products if p.task == ref.task and not p.built_from(ref)]
        return kills_products(tasks[ref.task], ref.checks_dir, mine)

    todo = [d for d in drafts if d.key not in cache]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ref, result in zip(todo, pool.map(work, todo), strict=True):
            cache[ref.key] = result
    if path is not None:
        path.write_text(json.dumps(cache, indent=1, sort_keys=True), encoding="utf-8")
    return render_o4b(run_o4b(drafts, labels, products, cache), len(products))


def render_o4b(o4: O4, products: int) -> str:
    lines = [
        "## O4b failing products as the mutants (added after the first run; no criterion)",
        "",
        f"- {products} saved products that failed exactly one hidden check; each is run against "
        "the drafts of its task except the draft it was built against",
        f"- all anchors present: {_interval(o4.present)}",
        f"- an anchor missing: {_interval(o4.missing)}",
        f"- gap {o4.gap:.1f} points",
    ]
    if o4.by_missing_type:
        lines += ["", "Kill rate when a rule has a missing anchor of this type:"]
        lines += [f"- {k}: {_interval(v)}" for k, v in o4.by_missing_type.items()]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.spec_eval", description=__doc__)
    parser.add_argument("steps", nargs="+", choices=(*STEPS, *EXTRA_STEPS, "all"))
    parser.add_argument("--tasks", type=Path, default=Path("bench/tasks"))
    parser.add_argument("--truth", type=Path, default=Path("bench/spec_truth"))
    parser.add_argument("--raw", type=Path, help="folder of saved cells (bench/results/raw)")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--population",
        choices=POPULATIONS,
        default="scored",
        help="scored: the 17 tasks CRITERIA.md fixed; held-out: the 18 later tasks, never pooled",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--cache", type=Path, help="kill results per draft, to resume a long run")
    args = parser.parse_args(argv)
    steps = tuple(args.steps)
    if "all" in steps:  # the five pre-registered steps, plus any extra one asked for by name
        steps = (*STEPS, *(x for x in steps if x in EXTRA_STEPS))
    try:
        text = run(
            steps,
            tasks_dir=args.tasks,
            truth_dir=args.truth,
            raw=args.raw,
            workers=args.workers,
            cache_path=args.cache,
            population=args.population,
        )
    except EvalError as exc:
        print(f"spec_eval: {exc}", file=sys.stderr)
        return 1
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
