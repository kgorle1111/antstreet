"""Which benchmark tasks a pull request touched, so CI validates only those.

Validating one task runs many short pytest processes (about 4 s each on a fast machine, 146 s for
the first 17 in CI), so a pull request that touches one task should not pay for all 43. Pushes to
main leave the variable unset and validate everything.
"""

import os
import subprocess
from pathlib import Path

ENV_VAR = "BOSS_VALIDATE_TASKS_SINCE"
ROOT = Path(__file__).resolve().parent.parent
TASK_DIRS = ("bench/tasks", "bench/tasks-multi")


def changed_task_ids(root: Path = ROOT) -> set[str] | None:
    """Ids of tasks whose files differ from the ref named by the env var, or None for "all".

    None whenever the answer cannot be trusted: no ref named, git missing, the ref unknown, or a
    changed file sitting directly in a tasks folder (so it belongs to no one task). Skipping a
    validation by mistake is the failure to avoid; validating too much only costs time.
    """
    ref = os.environ.get(ENV_VAR, "").strip()
    if not ref or ref.startswith("-"):  # a ref that looks like an option is never a ref
        return None
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{ref}...HEAD", "--", *TASK_DIRS],
            cwd=root, capture_output=True, text=True, check=True, timeout=60,
        ).stdout  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return None
    ids: set[str] = set()
    for line in out.splitlines():
        parts = Path(line).parts  # bench/<tasks|tasks-multi>/<id>/...
        if len(parts) < 4:
            return None
        ids.add(parts[2])
    return ids


def select(tasks: list, root: Path = ROOT) -> list:
    """The tasks to validate: all of them unless the env var names a base ref."""
    changed = changed_task_ids(root)
    return tasks if changed is None else [t for t in tasks if t.id in changed]
