"""Score a set of boss-written checks as a classifier of implementations. Pure: spends nothing.

Precision: a correct implementation, the task's reference, must pass every check. A check it fails
is wrong: it demands something the idea does not.
Recall: an incorrect implementation, one of the task's mutants, must fail at least one check.
A mutant that fails only wrong checks does not count as caught: a wrong check rejects everything,
so it detects nothing.
"""

from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from boss.bench.tasks import MUTANT_TIMEOUT_S, BenchTask
from boss.gate import Check, run_gate
from boss.roles.critic import GATE_TIMEOUT_S, Review

_KEYS = ("checks", "wrong", "mutants", "killed", "killed_only_by_wrong", "survived")


@dataclass(frozen=True, slots=True)
class DraftScore:
    checks: int  # boss checks in the draft
    wrong: tuple[str, ...]  # check ids the reference solution fails
    mutants: int
    killed: tuple[str, ...]  # mutants that fail at least one SOUND check (one the reference passes)
    killed_only_by_wrong: tuple[str, ...]  # mutants that fail only checks the reference also fails
    survived: tuple[str, ...]  # mutants that pass every check

    def __post_init__(self) -> None:
        if self.checks < 1 or self.mutants < 1:
            raise ValueError("a draft score needs at least one check and one mutant")
        if len(self.wrong) > self.checks:
            raise ValueError("more wrong checks than checks")
        sorted_mutants = len(self.killed) + len(self.killed_only_by_wrong) + len(self.survived)
        if sorted_mutants != self.mutants:
            raise ValueError("killed, killed_only_by_wrong and survived must add up to mutants")

    @property
    def precision(self) -> float:
        return (self.checks - len(self.wrong)) / self.checks

    @property
    def recall(self) -> float:
        return len(self.killed) / self.mutants

    @classmethod
    def from_dict(cls, raw: Any) -> DraftScore:
        """Rebuild a score saved with `asdict`; anything malformed raises ValueError."""
        if not isinstance(raw, dict) or set(raw) != set(_KEYS):
            raise ValueError(f"a draft score must have exactly the keys {list(_KEYS)}")
        for key in ("checks", "mutants"):
            if type(raw[key]) is not int:
                raise ValueError(f"draft score field {key!r} must be an int")
        for key in _KEYS[1:2] + _KEYS[3:]:
            names = raw[key]
            if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
                raise ValueError(f"draft score field {key!r} must be a list of names")
        return cls(**{k: tuple(v) if isinstance(v, list) else v for k, v in raw.items()})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def draft_checks(checks_dir: Path) -> list[Check]:
    """The checks in a draft's folder, named as `boss` names them: test_c01.py is check c01."""
    files = sorted(p.name for p in checks_dir.glob("test_*.py")) if checks_dir.is_dir() else []
    return [Check(name.removesuffix(".py").removeprefix("test_"), name) for name in files]


def _wrong_ids(task: BenchTask, checks_dir: Path, checks: list[Check]) -> set[str]:
    return {r.check_id for r in run_gate(task.reference_dir, checks_dir, checks) if not r.passed}


def count_wrong_checks(task: BenchTask, checks_dir: Path) -> int | None:
    """How many of the boss's checks the reference solution fails. None if no draft was written.

    Scoring only: the reference is copied by the gate into a temp folder, as for hidden checks.
    """
    checks = draft_checks(checks_dir)
    return len(_wrong_ids(task, checks_dir, checks)) if checks else None


def score_draft(task: BenchTask, checks_dir: Path) -> DraftScore:
    """Run the draft's checks on the reference and on every mutant: one gate run each."""
    checks = draft_checks(checks_dir)
    mutants = task.mutants()
    if not checks:
        raise ValueError(f"no checks (test_*.py) in {checks_dir}")
    if not mutants:
        raise ValueError(f"task {task.id} has no mutants to score against")
    wrong = _wrong_ids(task, checks_dir, checks)
    killed: list[str] = []
    only_wrong: list[str] = []
    survived: list[str] = []
    for mutant in mutants:
        results = run_gate(mutant, checks_dir, checks, timeout_s=MUTANT_TIMEOUT_S)
        failed = {r.check_id for r in results if not r.passed}
        if failed - wrong:
            killed.append(mutant.name)
        elif failed:
            only_wrong.append(mutant.name)
        else:
            survived.append(mutant.name)
    return DraftScore(
        checks=len(checks),
        wrong=tuple(sorted(wrong)),
        mutants=len(mutants),
        killed=tuple(killed),
        killed_only_by_wrong=tuple(only_wrong),
        survived=tuple(survived),
    )


@dataclass(frozen=True, slots=True)
class ReviewScore:
    """A critic's verified findings scored against the task's reference solution. Pure: spends
    nothing. A verified finding is WRONG when its test also fails on the reference: it demands
    something a correct product does not do."""

    verified: tuple[str, ...]  # finding ids, in the review's order
    wrong: tuple[str, ...]  # of those, the ones whose test the reference does not pass

    def __post_init__(self) -> None:
        if len(set(self.verified)) != len(self.verified) or not set(self.wrong) <= set(
            self.verified
        ):
            raise ValueError("wrong findings must be distinct and among the verified ones")

    @property
    def right(self) -> tuple[str, ...]:
        return tuple(f for f in self.verified if f not in self.wrong)

    @property
    def precision(self) -> float | None:
        """Right findings over verified ones. None when nothing was verified: no claim was made, so
        there is nothing to be right about. Sum `right` and `verified` across tasks, do not average
        this, or a critic that says nothing on most tasks looks perfect."""
        return len(self.right) / len(self.verified) if self.verified else None


def score_review(task: BenchTask, review: Review, timeout_s: float = GATE_TIMEOUT_S) -> ReviewScore:
    """Run each verified finding's test on the reference solution: one gate run in all. A test
    that does not pass there (fails, cannot import, or times out) makes its finding wrong."""
    findings = review.verified
    if not findings:
        return ReviewScore((), ())
    with tempfile.TemporaryDirectory(prefix="boss_bench_review_") as tmp:
        checks_dir = Path(tmp)
        for finding in findings:
            (checks_dir / finding.file).write_text(finding.test_code, encoding="utf-8")
        checks = [Check(f.id, f.file) for f in findings]
        results = run_gate(task.reference_dir, checks_dir, checks, timeout_s=timeout_s)
    return ReviewScore(
        tuple(f.id for f in findings), tuple(r.check_id for r in results if not r.passed)
    )
