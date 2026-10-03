"""Benchmark task format and validation.

A task is a folder:

    <id>/idea.md            the idea, including the exact module and function names to create
    <id>/meta.json          {"id", "title", "difficulty"}
    <id>/hidden_checks/     pytest files used only for scoring; never shown to either arm
    <id>/reference/         a solution proving the hidden checks can all pass; never shown either
    <id>/mutants/<name>/    known-wrong solutions, one folder each, laid out like reference/; used
                            only to score how well a boss's checks catch wrong code

Validation runs the gate on an empty workspace, the reference and every mutant: every hidden check
must fail on the empty one and pass on the reference, and every mutant must import and fail at
least one hidden check. A benchmark whose checks cannot pass, or pass for free, measures nothing;
a mutant that passes every hidden check is not wrong.

An imported task (`meta.json` has an `imported` key) comes from an external benchmark and is graded
by that benchmark's own test suite instead:

    <id>/idea.md     the external spec, shown to both arms
    <id>/hidden/     the whole pytest tree, subfolders and data files included; never shown
    <id>/support/    optional harness-owned files laid over the product root while grading

It has no reference and no mutants. Its tests are copied into a copy of the product at
`imported.test_path` and graded one by one (`grade_imported`).
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from boss.gate import Check, run_gate, run_tree
from boss.termsheet import CheckSpec, check_file_problems

MIN_HIDDEN_CHECKS = 5
MIN_MUTANTS = 3
MUTANT_TIMEOUT_S = 10.0  # per check; a wrong solution that hangs a check has failed it
MUTANTS_DIR = "mutants"
DIFFICULTIES = ("easy", "medium", "hard")
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}\Z")
_MUTANT_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,60}\Z")
_META_KEYS = {"id", "title", "difficulty"}
_IMPORTED_KEYS = {"source", "test_path", "test_count"}
IMPORTED_SOURCES = ("nl2repo",)


class TaskError(Exception):
    def __init__(self, task: str, problems: list[str]) -> None:
        super().__init__(f"task {task}: " + "; ".join(problems))
        self.problems = problems


@dataclass(frozen=True, slots=True)
class ImportedMeta:
    source: str  # one of IMPORTED_SOURCES
    test_path: str  # where the hidden tree goes inside the product, e.g. "tests"
    test_count: int  # tests the external suite has; a shortfall in a run counts as failed


@dataclass(frozen=True, slots=True)
class BenchTask:
    id: str
    title: str
    difficulty: str
    root: Path
    imported: ImportedMeta | None = None

    @property
    def idea(self) -> str:
        return (self.root / "idea.md").read_text(encoding="utf-8").strip()

    @property
    def hidden_dir(self) -> Path:
        return self.root / ("hidden" if self.imported else "hidden_checks")

    @property
    def support_dir(self) -> Path:
        return self.root / "support"

    @property
    def reference_dir(self) -> Path:
        return self.root / "reference"

    @property
    def mutants_dir(self) -> Path:
        return self.root / MUTANTS_DIR

    def mutants(self) -> list[Path]:
        """Each mutant's folder: a workspace holding a wrong solution, like `reference/`."""
        if not self.mutants_dir.is_dir():
            return []
        return sorted(
            p for p in self.mutants_dir.iterdir() if p.is_dir() and p.name != "__pycache__"
        )

    def hidden_checks(self) -> list[Check]:
        if self.imported:  # one pytest tree, graded per test by `grade_imported`, not per file
            return []
        files = sorted(p.name for p in self.hidden_dir.glob("test_*.py"))
        return [Check(name.removesuffix(".py").removeprefix("test_"), name) for name in files]


def load_task(root: Path) -> BenchTask:
    try:
        meta = json.loads((root / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TaskError(root.name, [f"meta.json unreadable: {exc}"]) from exc
    if not isinstance(meta, dict) or not _META_KEYS <= set(meta) <= _META_KEYS | {"imported"}:
        raise TaskError(root.name, [f"meta.json must have exactly the keys {sorted(_META_KEYS)}"])
    if not all(isinstance(meta[k], str) for k in _META_KEYS):
        raise TaskError(root.name, ["meta.json values must be strings"])
    imported = _load_imported(root.name, meta["imported"]) if "imported" in meta else None
    return BenchTask(meta["id"], meta["title"], meta["difficulty"], root, imported)


def _load_imported(task: str, raw: object) -> ImportedMeta:
    if not isinstance(raw, dict) or set(raw) != _IMPORTED_KEYS:
        raise TaskError(task, [f"meta.json imported must have exactly {sorted(_IMPORTED_KEYS)}"])
    count = raw["test_count"]
    if type(count) is not int or count < 1:
        raise TaskError(task, ["imported.test_count must be a whole number of at least 1"])
    if not all(isinstance(raw[k], str) for k in ("source", "test_path")):
        raise TaskError(task, ["imported.source and imported.test_path must be strings"])
    return ImportedMeta(raw["source"], raw["test_path"], count)


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
    if task.imported:  # an external spec may embed code; both arms see it equally
        return p + _imported_problems(task, task.imported)
    if "def test_" in task.idea:
        p.append("idea.md contains test code; hidden checks must stay hidden")
    checks = task.hidden_checks()
    if len(checks) < MIN_HIDDEN_CHECKS:
        p.append(f"needs at least {MIN_HIDDEN_CHECKS} hidden checks, has {len(checks)}")
    for check in checks:
        p += check_file_problems(CheckSpec(check.id, "", check.file, "bench"), task.hidden_dir)
    p += _reference_problems(task)
    p += _mutant_problems(task)
    return p


def _reference_problems(task: BenchTask) -> list[str]:
    sources = sorted(task.reference_dir.glob("*.py")) if task.reference_dir.is_dir() else []
    if not sources:
        return ["reference/ must contain the reference solution"]
    return _source_problems("reference/", sources)


def _source_problems(label: str, sources: list[Path]) -> list[str]:
    local = {s.stem for s in sources}
    problems = []
    for source in sources:
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            problems.append(f"{label}{source.name} has a syntax error on line {exc.lineno}")
            continue
        except UnicodeDecodeError:
            problems.append(f"{label}{source.name} is not valid UTF-8")
            continue
        for module in sorted(_imported_modules(tree) - local - sys.stdlib_module_names):
            problems.append(f"{label}{source.name} imports {module!r}, which is not stdlib")
    return problems


def _mutant_problems(task: BenchTask) -> list[str]:
    """Static checks on the wrong solutions. Whether they import and really fail comes later."""
    mutants = task.mutants()
    p = []
    if len(mutants) < MIN_MUTANTS:
        p.append(f"needs at least {MIN_MUTANTS} mutants, has {len(mutants)}")
    strays = [x.name for x in task.mutants_dir.glob("*") if x.is_file()]
    if strays:
        p.append(f"mutants/ must hold only folders, found {sorted(strays)}")
    modules = {s.name for s in task.reference_dir.glob("*.py")}
    for mutant in mutants:
        if not _MUTANT_RE.match(mutant.name):
            p.append(f"mutant name {mutant.name!r} must be lowercase letters, digits, underscores")
        sources = sorted(mutant.glob("*.py"))
        p += [
            f"mutants/{mutant.name}/ is missing {name}"
            for name in sorted(modules - {s.name for s in sources})
        ]
        p += _source_problems(f"mutants/{mutant.name}/", sources)
    return p


def _imported_modules(tree: ast.Module) -> set[str]:
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return modules


def gate_problems(task: BenchTask) -> list[str]:
    if task.imported:
        return _imported_gate_problems(task, task.imported)
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
    return problems + _mutant_gate_problems(task, checks)


def _mutant_gate_problems(task: BenchTask, checks: list[Check]) -> list[str]:
    mutants = task.mutants()
    if not mutants:
        return []

    modules = sorted(s.stem for s in task.reference_dir.glob("*.py"))

    def check(mutant: Path) -> str | None:
        if broken := _import_problem(mutant, modules):
            return f"mutant {mutant.name} does not import cleanly ({broken})"
        results = run_gate(mutant, task.hidden_dir, checks, timeout_s=MUTANT_TIMEOUT_S)
        if all(r.passed for r in results):
            return f"mutant {mutant.name} passes every hidden check, so it is not a wrong solution"
        return None

    # Each gate run is its own pytest processes, so threads only wait; this keeps validation quick.
    with ThreadPoolExecutor(max_workers=min(8, len(mutants))) as pool:
        return [problem for problem in pool.map(check, mutants) if problem]


def _import_problem(mutant: Path, modules: list[str]) -> str | None:
    """Why the mutant's modules cannot be imported, or None. Runs in its own interpreter."""
    code = "import importlib, sys\nsys.path.insert(0, sys.argv[1])\n" + (
        "for name in sys.argv[2:]:\n    importlib.import_module(name)\n"
    )
    with tempfile.TemporaryDirectory(prefix="boss_bench_import_") as cwd:
        try:
            done = subprocess.run(
                [sys.executable, "-I", "-B", "-c", code, str(mutant.resolve()), *modules],
                cwd=cwd,
                env={"PATH": "/usr/bin:/bin"},
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return "import took more than 30s"
    if done.returncode == 0:
        return None
    return (done.stderr.strip().splitlines() or [f"exit {done.returncode}"])[-1]


# Third-party test imports the gate's interpreter lacks, and the module that stands in for each.
# Written into `support/` by the converter; a missing one makes every test that imports it fail.
SHIMS = {"mock": "from unittest.mock import *  # noqa: F403  (the backport is the stdlib module)\n"}


def _imported_problems(task: BenchTask, meta: ImportedMeta) -> list[str]:
    p: list[str] = []
    if meta.source not in IMPORTED_SOURCES:
        p.append(f"imported.source must be one of {IMPORTED_SOURCES}")
    rel = PurePosixPath(meta.test_path)
    if rel.is_absolute() or ".." in rel.parts or rel.parts in ((), (".",)):
        p.append("imported.test_path must be a relative path inside the product")
    if not task.hidden_dir.is_dir():
        return [*p, "hidden/ must hold the pytest tree"]
    p += [
        f"{f.relative_to(task.root)} is a symlink; the tree must be plain files"
        for tree in (task.hidden_dir, task.support_dir)
        for f in sorted(tree.rglob("*"))
        if f.is_symlink()
    ]
    for source in sorted(task.hidden_dir.rglob("*.py")):
        try:
            ast.parse(source.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            p.append(f"hidden/{source.relative_to(task.hidden_dir)} does not parse: {exc}")
    if p:
        return p
    counted = _static_test_count(task.hidden_dir)
    if counted is not None and counted != meta.test_count:
        p.append(f"hidden/ defines {counted} tests but imported.test_count says {meta.test_count}")
    return p


def _test_files(tree: Path) -> list[str]:
    """Paths (posix, relative to the tree) of the files pytest collects tests from."""
    found = (p for p in tree.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(
        p.relative_to(tree).as_posix()
        for p in found
        if p.name.startswith("test_") or p.name.endswith("_test.py")
    )


def _static_test_count(tree: Path) -> int | None:
    """Tests the tree defines, read from the source; None when a parametrize is not a literal list
    (the count then needs a run, and a run needs the product)."""
    total = 0
    for name in _test_files(tree):
        for node in ast.parse((tree / name).read_text(encoding="utf-8")).body:
            in_class = isinstance(node, ast.ClassDef) and node.name.startswith("Test")
            for fn in node.body if isinstance(node, ast.ClassDef) and in_class else [node]:
                if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef) and fn.name.startswith(
                    "test"
                ):
                    cases = _cases(fn)
                    if cases is None:
                        return None
                    total += cases
    return total


def _cases(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    n = 1
    for deco in fn.decorator_list:
        if isinstance(deco, ast.Call) and getattr(deco.func, "attr", "") == "parametrize":
            values = deco.args[1] if len(deco.args) > 1 else None
            if not isinstance(values, ast.List | ast.Tuple):
                return None
            n *= len(values.elts)
    return n


def _imported_gate_problems(task: BenchTask, meta: ImportedMeta) -> list[str]:
    """An empty product must pass nothing, and the suite must have run at all: a sandbox or an
    import the gate lacks that kills every test would otherwise look like a hard task."""
    support = task.support_dir if task.support_dir.is_dir() else None
    with tempfile.TemporaryDirectory(prefix="boss_bench_empty_") as empty:
        got = run_tree(Path(empty), task.hidden_dir, meta.test_path, support=support)
    if not got.tests:
        return [f"hidden tree produced no results on an empty product ({got.detail})"]
    seen = {node.split("::")[0] for node in got.tests}
    problems = [
        f"hidden/{path} was not collected on an empty product"
        for path in _test_files(task.hidden_dir)
        if f"{meta.test_path}/{path}" not in seen
    ]
    if passing := sum(s == "passed" for s in got.tests.values()):
        problems.append(f"{passing} hidden tests pass on an empty product")
    problems += [
        f"hidden tests import {m!r}, which the gate lacks; support/{m}.py must stand in for it"
        for m in got.missing_modules
        if m in SHIMS
    ]
    return problems


def grade_imported(task: BenchTask, workspace: Path) -> dict[str, str]:
    """Node id -> status of every hidden test on this product, always `test_count` entries or more.

    A test that never ran (collection error, timeout, a missing product) is a failure, so the pass
    fraction is over the suite and not over whatever happened to get collected.
    """
    meta = task.imported
    assert meta is not None  # callers branch on task.imported
    support = task.support_dir if task.support_dir.is_dir() else None
    seen: dict[str, str] = {}
    if workspace.is_dir():
        run = run_tree(workspace, task.hidden_dir, meta.test_path, support=support)
        seen = {node: str(status) for node, status in run.tests.items()}
    for i in range(1, meta.test_count - len(seen) + 1):
        seen[f"(not run {i})"] = "failed"
    return seen


def task_set_hash(tasks: list[BenchTask]) -> str:
    """One hash for the whole task set, recorded in every result so results name what they ran.

    Covers what an arm is scored against: the idea, hidden checks and reference. Mutants are left
    out on purpose: no arm ever sees or is scored on them, so adding one must not make old and new
    results look like they ran against different tasks.
    """
    digest = hashlib.sha256()
    for task in sorted(tasks, key=lambda t: t.id):
        for path in sorted(task.root.rglob("*")):
            skipped = "__pycache__" in path.parts or path.is_relative_to(task.mutants_dir)
            if path.is_file() and not skipped:
                # Length-prefixed, so where a name ends and its content begins is unambiguous.
                for part in (str(path.relative_to(task.root.parent)).encode(), path.read_bytes()):
                    digest.update(len(part).to_bytes(8, "big") + part)
    return digest.hexdigest()[:16]
