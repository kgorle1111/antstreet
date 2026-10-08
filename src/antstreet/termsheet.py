"""The term sheet: an idea turned into executable checks, tasks and funding rounds.

The boss drafts it, the investor approves it, and nothing is funded until it validates. Validation
collects every problem instead of stopping at the first, so one review round fixes them all.
"""

from __future__ import annotations

import ast
import json
import re
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields
from itertools import combinations, product
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from antstreet.gate import Check, CheckStatus, run_gate

if TYPE_CHECKING:
    from antstreet.dispatch import DispatchPolicy

_CHECK_FILE_RE = re.compile(r"^test_[A-Za-z0-9_]+\.py\Z")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}\Z")
# A story's criterion as roles.stories numbers it (S2.1), or a rule of the request as antstreet.spec
# numbers it (R07). One field, two namespaces: a run uses one or the other.
_CRITERION_ID_RE = re.compile(r"(?:S[1-9]\d?\.[1-9]\d*|R(?:0[1-9]|[1-9]\d))\Z")


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
    criteria: tuple[str, ...] = ()  # acceptance criteria it verifies; left out of the JSON if empty

    def __post_init__(self) -> None:
        _types(self, id=str, description=str, file=str, task=str, criteria=tuple)
        for criterion in self.criteria:
            if not isinstance(criterion, str) or not _CRITERION_ID_RE.match(criterion):
                raise ValueError(f"CheckSpec.criteria: {criterion!r} is not a criterion id")
        if len(set(self.criteria)) != len(self.criteria):
            raise ValueError(f"CheckSpec.criteria repeats an id: {self.criteria!r}")


@dataclass(frozen=True, slots=True)
class Dispatch:
    """How one task is worked on (`boss fund --dispatch rules`). Values are checked against the
    whitelist by `dispatch.dispatch_problems`, not here, so a bad edit reports every problem."""

    agent: str
    profile: str | None
    tier: str
    effort: str
    escalate_to: str  # "none", or the tier a worker fired for no progress may be replaced by
    max_workers: int
    slice_micros: int | None  # None: the run's --slice
    reads: tuple[str, ...]  # ids of other tasks whose interface names this task is shown

    def __post_init__(self) -> None:
        _types(self, agent=str, profile=(str, type(None)), tier=str, effort=str, escalate_to=str)
        _types(self, max_workers=int, slice_micros=(int, type(None)), reads=tuple)
        if not all(isinstance(r, str) for r in self.reads):
            raise TypeError("Dispatch.reads must be strings")


@dataclass(frozen=True, slots=True)
class Task:
    id: str
    brief: str
    paths: tuple[str, ...]  # workspace paths this task owns; "." means the whole workspace
    dispatch: Dispatch | None = None  # left out of the JSON if None

    def __post_init__(self) -> None:
        _types(self, id=str, brief=str, paths=tuple, dispatch=(Dispatch, type(None)))
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
    route: str | None = None  # "one_agent" or "firm" under --dispatch; left out of the JSON if None

    def __post_init__(self) -> None:
        _types(
            self,
            idea=str,
            budget_micros=int,
            rounds=tuple,
            checks=tuple,
            tasks=tuple,
            approved_by_investor=bool,
            route=(str, type(None)),
        )

    def gate_checks(self) -> list[Check]:
        return [Check(c.id, c.file) for c in self.checks]

    def to_json(self) -> str:
        data = asdict(self)
        for check in data["checks"]:
            if not check["criteria"]:
                del check["criteria"]  # older sheets keep the JSON their approval hashes cover
        for task in data["tasks"]:
            if task["dispatch"] is None:
                del task["dispatch"]
        if data["route"] is None:
            del data["route"]
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, text: str) -> TermSheet:
        try:
            raw = json.loads(text)
            return cls(
                **_fields(raw, cls, nested=("rounds", "checks", "tasks"), optional=("route",)),
                rounds=tuple(Round(**_fields(r, Round)) for r in raw["rounds"]),
                checks=tuple(_check_from(c) for c in raw["checks"]),
                tasks=tuple(_task_from(t) for t in raw["tasks"]),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise TermSheetError([f"not a valid term sheet: {exc}"]) from exc


def _task_from(raw: Any) -> Task:
    data = _fields(raw, Task, optional=("dispatch",))
    found, dispatch = data.get("dispatch"), None
    if found is not None:
        d = _fields(found, Dispatch)
        dispatch = Dispatch(**d | {"reads": tuple(as_list(d["reads"]))})
    return Task(**data | {"paths": tuple(as_list(data["paths"])), "dispatch": dispatch})


def _check_from(raw: Any) -> CheckSpec:
    data = _fields(raw, CheckSpec, optional=("criteria",))
    return CheckSpec(**data | {"criteria": tuple(as_list(data.get("criteria", [])))})


def as_list(value: object) -> list[Any]:
    # tuple("rev.py") would silently become ("r", "e", "v", ...); insist on a JSON array.
    if not isinstance(value, list):
        raise TypeError(f"expected a list, got {type(value).__name__}")
    return value


def _fields(
    raw: Any, cls: type, nested: tuple[str, ...] = (), optional: tuple[str, ...] = ()
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError(f"{cls.__name__} must be an object")
    expected = {f.name for f in fields(cls)} - (set(optional) - set(raw))
    if set(raw) != expected:
        raise ValueError(f"{cls.__name__} fields differ: {sorted(set(raw) ^ expected)}")
    return {k: v for k, v in raw.items() if k not in nested}


def validate(sheet: TermSheet, checks_dir: Path, policy: DispatchPolicy | None = None) -> None:
    """Raise TermSheetError listing every problem. Runs the gate only if the structure is sound.
    `policy` is the run's dispatch policy; None means `--dispatch` is off."""
    problems = structural_problems(sheet, checks_dir, policy)
    if not problems:
        problems = empty_workspace_problems(sheet, checks_dir)
    if problems:
        raise TermSheetError(problems)


def structural_problems(
    sheet: TermSheet, checks_dir: Path, policy: DispatchPolicy | None = None
) -> list[str]:
    from antstreet.dispatch import dispatch_problems  # dispatch imports this module

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
    p += dispatch_problems(sheet, policy)
    for check in sheet.checks:
        p += check_file_problems(check, checks_dir)
    return p


def empty_workspace_problems(sheet: TermSheet, checks_dir: Path) -> list[str]:
    """A check that passes (or hangs) before any work is done cannot measure progress."""
    return empty_checks_problems(sheet.gate_checks(), checks_dir)


def empty_checks_problems(checks: Sequence[Check], checks_dir: Path) -> list[str]:
    """`empty_workspace_problems` for any list of checks: the held-out checks use it too."""
    with tempfile.TemporaryDirectory(prefix="boss_empty_ws_") as empty:
        results = run_gate(Path(empty), checks_dir, checks, timeout_s=30.0)
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
    return p + _overlap_problems(sheet)


def _overlap_problems(sheet: TermSheet) -> list[str]:
    """One line per pair of tasks that own the same path or a path and its parent directory.

    Paths that leave the workspace are skipped here; _ownership_problems already reports them.
    """
    p: list[str] = []
    for a, b in combinations(sheet.tasks, 2):
        for path_a, path_b in product(_inside(a), _inside(b)):
            pure_a, pure_b = PurePosixPath(path_a), PurePosixPath(path_b)
            if _contains(pure_a, pure_b):
                p.append(f"tasks {a.id} and {b.id} both own {path_a}")
                break
            if _contains(pure_b, pure_a):
                p.append(f"tasks {a.id} and {b.id} both own {path_b}")
                break
    return p


def _inside(task: Task) -> list[str]:
    return [
        path
        for path in task.paths
        if path.strip()
        and not PurePosixPath(path).is_absolute()
        and ".." not in PurePosixPath(path).parts
    ]


def _contains(parent: PurePosixPath, child: PurePosixPath) -> bool:
    """True if child is parent or lies under it; the root path "." contains everything."""
    return parent == child or parent == PurePosixPath(".") or parent in child.parents


def check_file_problems(check: CheckSpec, checks_dir: Path) -> list[str]:
    if not _CHECK_FILE_RE.match(check.file):
        return [f"check {check.id} file {check.file!r} must be named test_<name>.py"]
    path = checks_dir / check.file
    if not path.is_file():
        return [f"check {check.id} file {check.file} does not exist"]
    # The gate resolves symlinks and refuses any that leave the directory; say so here, early.
    if not path.resolve().is_relative_to(checks_dir.resolve()):
        return [f"check {check.id} file {check.file} points outside the checks directory"]
    try:
        # utf-8-sig: a BOM is legal for python and pytest, so it must not reach the parser as text.
        tree = ast.parse(path.read_bytes().decode("utf-8-sig"), filename=check.file)
    except UnicodeDecodeError as exc:
        return [f"check {check.id} is not valid UTF-8: {exc.reason} at byte {exc.start}"]
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
