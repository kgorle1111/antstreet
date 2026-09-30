"""Benchmark task format and validation.

A task is a folder:

    <id>/idea.md            the idea, including the exact module and function names to create
    <id>/meta.json          {"id", "title", "difficulty"}
    <id>/hidden_checks/     pytest files used only for scoring; never shown to either arm
    <id>/reference/         a solution proving the hidden checks can all pass; never shown either

Validation runs the gate twice: every hidden check must fail on an empty workspace and pass on
the reference. A benchmark whose checks cannot pass, or pass for free, measures nothing.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from boss.gate import Check, run_gate
from boss.termsheet import CheckSpec, check_file_problems

MIN_HIDDEN_CHECKS = 5
DIFFICULTIES = ("easy", "medium", "hard")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}\Z")
_META_KEYS = {"id", "title", "difficulty"}


class TaskError(Exception):
    def __init__(self, task: str, problems: list[str]) -> None:
        super().__init__(f"task {task}: " + "; ".join(problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class BenchTask:
    id: str
    title: str
    difficulty: str
    root: Path

    @property
    def idea(self) -> str:
        return (self.root / "idea.md").read_text(encoding="utf-8").strip()

    @property
    def hidden_dir(self) -> Path:
        return self.root / "hidden_checks"

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"

    def hidden_checks(self) -> list[Check]:
        files = sorted(p.name for p in self.hidden_dir.glob("test_*.py"))
        return [Check(name.removesuffix(".py").removeprefix("test_"), name) for name in files]


def load_task(root: Path) -> BenchTask:
    try:
        meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TaskError(root.name, [f"meta.json unreadable: {exc}"]) from exc
    if not isinstance(meta, dict) or set(meta) != _META_KEYS:
        raise TaskError(root.name, [f"meta.json must have exactly the keys {sorted(_META_KEYS)}"])
    if not all(isinstance(meta[k], str) for k in _META_KEYS):
        raise TaskError(root.name, ["meta.json values must be strings"])
    return BenchTask(meta["id"], meta["title"], meta["difficulty"], root)


def load_tasks(tasks_dir: Path) -> list[BenchTask]:
    return [load_task(p) for p in sorted(tasks_dir.iterdir()) if (p / "meta.json").is_file()]


def validate_task(task: BenchTask) -> None:
    problems = structural_problems(task) or gate_problems(task)
    if problems:
        raise TaskError(task.id, problems)


def structural_problems(task: BenchTask) -> list[str]:
    p: list[str] = []
    if not _ID_RE.match(task.id) or task.id != task.root.name:
        p.append(f"id {task.id!r} must be lowercase-with-dashes and equal the folder name")
    if not task.title.strip():
        p.append("title is empty")
    if task.difficulty not in DIFFICULTIES:
        p.append(f"difficulty must be one of {DIFFICULTIES}")
    idea_file = task.root / "idea.md"
    if not idea_file.is_file() or not task.idea:
        return [*p, "idea.md is missing or empty"]
    if task.idea.startswith("-"):
        p.append("idea.md must not start with '-'")
    if "def test_" in task.idea:
        p.append("idea.md contains test code; hidden checks must stay hidden")
    checks = task.hidden_checks()
    if len(checks) < MIN_HIDDEN_CHECKS:
        p.append(f"needs at least {MIN_HIDDEN_CHECKS} hidden checks, has {len(checks)}")
    for check in checks:
        p += check_file_problems(CheckSpec(check.id, "", check.file, "bench"), task.hidden_dir)
    p += _reference_problems(task)
    return p


def _reference_problems(task: BenchTask) -> list[str]:
    sources = sorted(task.reference_dir.glob("*.py")) if task.reference_dir.is_dir() else []
    if not sources:
        return ["reference/ must contain the reference solution"]
    local = {s.stem for s in sources}
    problems = []
    for source in sources:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"reference/{source.name} has a syntax error on line {exc.lineno}")
            continue
        for module in sorted(_imported_modules(tree) - local - sys.stdlib_module_names):
            problems.append(f"reference/{source.name} imports {module!r}, which is not stdlib")
    return problems


def _imported_modules(tree: ast.Module) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def gate_problems(task: BenchTask) -> list[str]:
    checks = task.hidden_checks()
    with tempfile.TemporaryDirectory(prefix="boss_bench_empty_") as empty:
        on_empty = run_gate(Path(empty), task.hidden_dir, checks, timeout_s=30.0)
    on_reference = run_gate(task.reference_dir, task.hidden_dir, checks, timeout_s=30.0)
    problems = [
        f"hidden check {r.check_id} does not fail on an empty workspace ({r.status})"
        for r in on_empty
        if r.status != "failed"
    ]
    problems += [
        f"hidden check {r.check_id} does not pass on the reference ({r.detail})"
        for r in on_reference
        if not r.passed
    ]
    return problems


def task_set_hash(tasks: list[BenchTask]) -> str:
    """One hash for the whole task set, recorded in every result so results name what they ran."""
    digest = hashlib.sha256()
    for task in sorted(tasks, key=lambda t: t.id):
        for path in sorted(task.root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digest.update(str(path.relative_to(task.root.parent)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()[:16]
