"""Validate every task in a folder: `python -m antstreet.bench.validate DIR [--strict]`.

Plain mode is `validate_task` as CI runs it. `--strict` is for private task sets whose logs nobody
can reread: the reference must pass 3 times, no hidden check may take over 1 s on it, there must be
at least 8 mutants, and a mutant counts as killed only by a failing check, never by a timeout.
Exit 0 when every task passes, 1 when any fails, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from antstreet.bench.tasks import (
    VALIDATE_TIMEOUT_S,
    BenchTask,
    TaskError,
    load_task,
    validate_task,
)
from antstreet.gate import GateError, run_gate

STRICT: dict[str, Any] = {
    "reference_runs": 3,
    "check_budget_s": 1.0,
    "min_mutants": 8,
    "timeout_kills": False,
}


def _slowest(task: BenchTask) -> str:
    """The reference's slowest hidden check, from an extra gate run."""
    if task.imported:
        return "slowest check n/a (imported task)"
    try:
        results = run_gate(
            task.reference_dir, task.hidden_dir, task.hidden_checks(), timeout_s=VALIDATE_TIMEOUT_S
        )
    except GateError as exc:  # the task already passed; a timing line is not worth the summary
        return f"slowest check n/a ({exc})"
    worst = max(results, key=lambda r: r.duration_s, default=None)
    if worst is None:
        return "slowest check n/a (no checks)"
    return f"slowest check {worst.check_id} {worst.duration_s:.2f}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m antstreet.bench.validate", description=__doc__)
    parser.add_argument("dir", type=Path, help="folder holding one sub-folder per task")
    parser.add_argument(
        "--strict", action="store_true", help="reference x3, 1 s/check, >=8 mutants"
    )
    args = parser.parse_args(argv)
    if not args.dir.is_dir():
        print(
            f"error: {args.dir} is not a folder; pass the folder that holds the task folders",
            file=sys.stderr,
        )
        return 2
    folders = sorted(p for p in args.dir.iterdir() if (p / "meta.json").is_file())
    if not folders:
        print(
            f"error: no tasks in {args.dir} (a task folder has a meta.json); nothing validated",
            file=sys.stderr,
        )
        return 2
    options = STRICT if args.strict else {}
    failed = 0
    for folder in folders:
        try:
            task = load_task(folder)
        except TaskError as exc:  # one malformed task must not hide the verdict on the others
            failed += 1
            print(f"FAIL {folder.name}")
            for problem in exc.problems:
                print(f"  - {problem}")
            continue
        try:
            validate_task(task, **options)
        except TaskError as exc:
            failed += 1
            print(f"FAIL {task.id}")
            for problem in exc.problems:
                print(f"  - {problem}")
            continue
        print(f"ok   {task.id}  {_slowest(task)}")
    mode = " (strict)" if args.strict else ""
    print(f"{len(folders) - failed} of {len(folders)} tasks passed{mode}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
