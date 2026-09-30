"""The term sheet: an idea turned into executable checks, tasks and funding rounds.

The boss drafts it, the investor approves it, and nothing is funded until it validates. Validation
collects every problem instead of stopping at the first, so one review round fixes them all.
"""

from __future__ import annotations

import ast
import json
import re
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any

from boss.gate import Check, CheckStatus, run_gate

_CHECK_FILE_RE = re.compile(r"^test_[A-Za-z0-9_]+\.py$")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


class TermSheetError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def _types(obj: object, **expected: type | tuple[type, ...]) -> None:
    """Reject wrong JSON types at the boundary; bool is excluded from int on purpose."""
    for name, kind in expected.items():
        value = getattr(obj, name)
        if isinstance(value, bool) and kind is int or not isinstance(value, kind):
            raise TypeError(f"{type(obj).__name__}.{name} must be {kind}, got {value!r}")


@dataclass(frozen=True, slots=True)
class Round:
    n: int
    budget_micros: int
    unlock_checks: int  # passing checks needed to close this round and open the next

    def __post_init__(self) -> None:
        _types(self, n=int, budget_micros=int, unlock_checks=int)


@dataclass(frozen=True, slots=True)
class CheckSpec:
    id: str
    description: str
    file: str  # a file name inside the run's checks directory
    task: str

    def __post_init__(self) -> None:
        _types(self, id=str, description=str, file=str, task=str)


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    brief: str
    paths: tuple[str, ...]  # workspace paths this task owns; "." means the whole workspace

    def __post_init__(self) -> None:
        _types(self, id=str, brief=str, paths=tuple)
        if not all(isinstance(p, str) for p in self.paths):
            raise TypeError("Task.paths must be strings")


@dataclass(frozen=True, slots=True)
class TermSheet:
    idea: str
    budget_micros: int
    rounds: tuple[Round, ...]
    checks: tuple[CheckSpec, ...]
    tasks: tuple[Task, ...]
    approved_by_investor: bool = False

    def __post_init__(self) -> None:
        _types(
            self,
            idea=str,
            budget_micros=int,
            rounds=tuple,
            checks=tuple,
            tasks=tuple,
            approved_by_investor=bool,
        )

    def gate_checks(self) -> list[Check]:
        return [Check(c.id, c.file) for c in self.checks]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> TermSheet:
        try:
            raw = json.loads(text)
            return cls(
                **_fields(raw, cls, nested=("rounds", "checks", "tasks")),
                rounds=tuple(Round(**_fields(r, Round)) for r in raw["rounds"]),
                checks=tuple(CheckSpec(**_fields(c, CheckSpec)) for c in raw["checks"]),
                tasks=tuple(
                    Task(**_fields(t, Task) | {"paths": tuple(t["paths"])}) for t in raw["tasks"]
                ),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise TermSheetError([f"not a valid term sheet: {exc}"]) from exc


def _fields(raw: Any, cls: type, nested: tuple[str, ...] = ()) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError(f"{cls.__name__} must be an object")
    expected = {f.name for f in fields(cls)}
    if set(raw) != expected:
        raise ValueError(f"{cls.__name__} fields differ: {sorted(set(raw) ^ expected)}")
    return {k: v for k, v in raw.items() if k not in nested}


def validate(sheet: TermSheet, checks_dir: Path) -> None:
    """Raise TermSheetError listing every problem. Runs the gate only if the structure is sound."""
    problems = structural_problems(sheet, checks_dir)
    if not problems:
        problems = empty_workspace_problems(sheet, checks_dir)
    if problems:
        raise TermSheetError(problems)


def structural_problems(sheet: TermSheet, checks_dir: Path) -> list[str]:
    p: list[str] = []
    if not sheet.idea.strip():
        p.append("idea is empty")
    if not sheet.checks:
        p.append("no checks")
    if not sheet.tasks:
        p.append("no tasks")
    if not sheet.rounds:
        p.append("no rounds")
    p += _id_problems("check", [c.id for c in sheet.checks])
    p += _id_problems("task", [t.id for t in sheet.tasks])
    p += _money_problems(sheet)
    p += _round_problems(sheet)
    p += _ownership_problems(sheet)
    for check in sheet.checks:
        p += check_file_problems(check, checks_dir)
    return p


def empty_workspace_problems(sheet: TermSheet, checks_dir: Path) -> list[str]:
    """A check that passes (or hangs) before any work is done cannot measure progress."""
    with tempfile.TemporaryDirectory(prefix="boss_empty_ws_") as empty:
        results = run_gate(Path(empty), checks_dir, sheet.gate_checks(), timeout_s=30.0)
    return [
        f"check {r.check_id} {'passes' if r.passed else 'times out'} on an empty workspace"
        for r in results
        if r.status in (CheckStatus.PASSED, CheckStatus.TIMEOUT)
    ]


def _id_problems(kind: str, ids: list[str]) -> list[str]:
    p = [f"{kind} id {i!r} is invalid" for i in ids if not _ID_RE.match(str(i))]
    p += [f"duplicate {kind} id {i!r}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    return p


def _money_problems(sheet: TermSheet) -> list[str]:
    amounts = [sheet.budget_micros, *(r.budget_micros for r in sheet.rounds)]
    if any(type(a) is not int or a <= 0 for a in amounts):
        return ["budgets must be positive integers (micro-dollars)"]
    total = sum(r.budget_micros for r in sheet.rounds)
    if total != sheet.budget_micros:
        return [f"round budgets sum to {total}, term sheet budget is {sheet.budget_micros}"]
    return []


def _round_problems(sheet: TermSheet) -> list[str]:
    p: list[str] = []
    if [r.n for r in sheet.rounds] != list(range(1, len(sheet.rounds) + 1)):
        p.append("rounds must be numbered 1, 2, 3, ... in order")
    unlocks = [r.unlock_checks for r in sheet.rounds]
    if any(type(u) is not int or not 1 <= u <= len(sheet.checks) for u in unlocks):
        p.append(f"unlock_checks must be between 1 and the number of checks ({len(sheet.checks)})")
    elif unlocks != sorted(unlocks):
        p.append("unlock_checks must not decrease from one round to the next")
    elif unlocks and unlocks[-1] != len(sheet.checks):
        p.append("the last round must unlock only when every check passes")
    return p


def _ownership_problems(sheet: TermSheet) -> list[str]:
    task_ids = {t.id for t in sheet.tasks}
    p = [
        f"check {c.id} belongs to unknown task {c.task!r}"
        for c in sheet.checks
        if c.task not in task_ids
    ]
    owned = {c.task for c in sheet.checks}
    p += [
        f"task {t.id} owns no checks, so its progress cannot be measured"
        for t in sheet.tasks
        if t.id not in owned
    ]
    for task in sheet.tasks:
        if not task.paths:
            p.append(f"task {task.id} declares no paths")
        for path in task.paths:
            pure = PurePosixPath(path)
            if pure.is_absolute() or ".." in pure.parts or not path.strip():
                p.append(f"task {task.id} path {path!r} must stay inside the workspace")
    return p


def check_file_problems(check: CheckSpec, checks_dir: Path) -> list[str]:
    if not _CHECK_FILE_RE.match(check.file):
        return [f"check {check.id} file {check.file!r} must be named test_<name>.py"]
    path = checks_dir / check.file
    if not path.is_file():
        return [f"check {check.id} file {check.file} does not exist"]
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=check.file)
    except SyntaxError as exc:
        return [f"check {check.id} has a syntax error: line {exc.lineno}: {exc.msg}"]
    if not _defines_a_test(tree):
        return [f"check {check.id} defines no test_ function"]
    return []


def _defines_a_test(tree: ast.Module) -> bool:
    def is_test_fn(node: ast.stmt) -> bool:
        return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
            "test"
        )

    return any(
        is_test_fn(node)
        or (
            isinstance(node, ast.ClassDef)
            and node.name.startswith("Test")
            and any(is_test_fn(m) for m in node.body)
        )
        for node in tree.body
    )
