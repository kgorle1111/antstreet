"""Turn a task downloaded from an external benchmark into a bench task folder (see `tasks.py`).

    python -m boss.bench.imported nl2repo <task-dir> <dest-root>

writes `<dest-root>/<task-id>/` with `idea.md` (the spec), `hidden/` (its pytest tree), `meta.json`
and, where the tests import a module the gate lacks, `support/`. The source stays where it is and
nothing is fetched: external task data is never committed here, so `<dest-root>` belongs outside
the repository (the benchmark takes it with `--tasks`).

nl2repo task folder: `start.md`, `tests/`, `test_commands.json` (the last command is the pytest
run; its last word is the test path inside the product), `test_case_count.txt`.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from boss.bench.tasks import IMPORTED_SOURCES, SHIMS, TaskError, load_task, validate_task

_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc")


class ConvertError(Exception):
    """The source folder is not a task this converter understands. Says what is missing."""


def convert_nl2repo(src: Path, dest_root: Path, task_id: str | None = None) -> Path:
    task_id = task_id or src.name
    dest = dest_root / task_id
    if dest.exists():
        raise ConvertError(f"{dest} already exists; remove it to convert again")
    spec = _read(src / "start.md")
    count = _count(src / "test_case_count.txt")
    test_path = _test_path(src / "test_commands.json")
    tests = src / test_path
    if not tests.is_dir():
        raise ConvertError(f"{tests} is not a folder; test_commands.json names {test_path!r}")
    dest.mkdir(parents=True)
    (dest / "idea.md").write_text(spec.strip() + "\n", encoding="utf-8")
    shutil.copytree(tests, dest / "hidden", ignore=_IGNORE)
    for name in sorted(_imported_names(dest / "hidden") & SHIMS.keys()):
        (dest / "support").mkdir(exist_ok=True)
        (dest / "support" / f"{name}.py").write_text(SHIMS[name], encoding="utf-8")
    meta = {
        "id": task_id,
        "title": f"{task_id} (NL2Repo-Bench)",
        "difficulty": "hard",
        "imported": {"source": "nl2repo", "test_path": test_path, "test_count": count},
    }
    (dest / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return dest


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConvertError(f"cannot read {path}: {exc}") from exc


def _count(path: Path) -> int:
    try:
        return int(_read(path).strip())
    except ValueError as exc:
        raise ConvertError(f"{path} must hold one whole number") from exc


def _test_path(path: Path) -> str:
    try:
        commands = json.loads(_read(path))
    except ValueError as exc:
        raise ConvertError(f"{path} is not valid JSON") from exc
    pytest_runs = [c for c in commands if isinstance(c, str) and c.split()[:1] == ["pytest"]]
    if not isinstance(commands, list) or len(pytest_runs) != 1:
        raise ConvertError(f"{path} must list exactly one `pytest ...` command")
    return pytest_runs[0].split()[-1]


def _imported_names(tree: Path) -> set[str]:
    names: set[str] = set()
    for source in tree.rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boss.bench.imported", description=__doc__)
    parser.add_argument("source", choices=IMPORTED_SOURCES)
    parser.add_argument("task_dir", type=Path, help="the downloaded task folder")
    parser.add_argument("dest_root", type=Path, help="tasks folder to write into, outside the repo")
    parser.add_argument("--id", help="task id (default: the task folder's name)")
    args = parser.parse_args(argv)
    try:
        dest = convert_nl2repo(args.task_dir, args.dest_root, args.id)
        task = load_task(dest)
        print(f"wrote {dest}")
        validate_task(task)
    except (ConvertError, TaskError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"task {task.id} is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
