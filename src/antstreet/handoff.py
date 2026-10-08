"""Hand a fired worker's files and failure notes to its replacement, without a model call.

The replacement is offered the old files and may ignore them. Everything read from the old
attempt (its files, its note, the test output) is data, so nothing here instructs the new worker
except `reassignment_prompt`, and that only frames the data as quoted material.
"""

from __future__ import annotations

import os
import re
import shutil
import textwrap
from collections.abc import Sequence
from pathlib import Path

from antstreet.gate import CheckResult
from antstreet.redact import redact
from antstreet.rule import SliceRecord, Verdict
from antstreet.runner import FORBIDDEN_WORKSPACE_ENTRIES

PREVIOUS_DIR = "previous_attempt"
SKIPPED_NAMES = frozenset(
    {*FORBIDDEN_WORKSPACE_ENTRIES, "__pycache__", ".pytest_cache", PREVIOUS_DIR}
)
_TRUNCATED = "[notes truncated]"
_LAST_NOTE_CHARS = 500
_INDENT = "    "


def failure_notes(
    verdict: Verdict,
    history: Sequence[SliceRecord],
    gate_results: Sequence[CheckResult],
    last_reason: str | None,
    *,
    max_chars: int = 6000,
    tail_chars: int = 800,
) -> str:
    """Plain-text account of why the worker was stopped, redacted and at most `max_chars` long.

    Secrets are masked before any cut, so a truncation never leaves half a credential behind.
    """
    if max_chars < len(_TRUNCATED) + 1:
        raise ValueError(f"max_chars must be at least {len(_TRUNCATED) + 1}")
    passing = sorted(r.check_id for r in gate_results if r.passed)
    lines = [
        f"The previous builder was stopped: {verdict.reason} after {len(history)} slice(s).",
        f"Checks passing when it stopped: {', '.join(passing) if passing else 'none'}",
    ]
    for result in gate_results:
        if result.passed:
            continue
        lines.append(f"Check {result.check_id}: {result.status.value} ({result.detail})")
        tail = redact(result.output_tail)[-tail_chars:] if tail_chars > 0 else ""
        if tail.strip():
            lines.append(textwrap.indent(tail.rstrip("\n"), _INDENT))
    if last_reason and last_reason.strip():
        lines.append("The previous builder's own last note (its claim, not verified):")
        lines.append(textwrap.indent(redact(last_reason)[:_LAST_NOTE_CHARS], _INDENT))
    text = redact("\n".join(lines))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(_TRUNCATED) - 1] + "\n" + _TRUNCATED


def prepare_workspace(previous: Path, new: Path) -> list[str]:
    """Create `new` and copy the old attempt's regular files into `new / PREVIOUS_DIR`.

    Skips agent configuration, caches, earlier `previous_attempt` folders and symlinks (never
    followed), so the result passes `check_workspace`. Returns the sorted posix paths copied.
    """
    if new.exists() and (not new.is_dir() or any(new.iterdir())):
        raise ValueError(f"{new} exists and is not an empty directory")
    relative: list[Path] = []
    for root, dirs, files in os.walk(previous):  # followlinks=False: symlinked dirs stay unread
        dirs[:] = [d for d in dirs if d not in SKIPPED_NAMES]
        for name in files:
            path = Path(root, name)
            if name not in SKIPPED_NAMES and path.is_file() and not path.is_symlink():
                relative.append(path.relative_to(previous))
    new.mkdir(parents=True, exist_ok=True)
    for rel in relative:
        target = new / PREVIOUS_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(previous / rel, target)
    return sorted(rel.as_posix() for rel in relative)


def reassignment_prompt(task_prompt: str, notes: str, previous_files: Sequence[str]) -> str:
    """The task prompt followed by the failure notes as quoted material and the files on offer."""
    longest_run = max((len(m) for m in re.findall(r"`+", notes)), default=0)
    fence = "`" * max(3, longest_run + 1)  # a fence longer than any run in `notes` cannot be closed
    parts = [
        "A previous builder worked on this task and was stopped. Its failure notes follow as "
        "quoted material.",
        f"{fence}\n{notes}\n{fence}",
    ]
    if previous_files:
        listing = "\n".join(f"- {_printable(name)}" for name in previous_files)
        parts.append(
            f"The files it left are in {PREVIOUS_DIR}/:\n{listing}\n"
            "You may read and reuse them or ignore them. The files you own must be created at "
            f"the workspace root as the task says, NOT inside {PREVIOUS_DIR}/."
        )
    else:
        parts.append("It left no files.")
    prompt = task_prompt + "\n\n" + "\n\n".join(parts)
    return f"Task:\n{prompt}" if prompt.startswith("-") else prompt


def _printable(name: str) -> str:
    """File names come from the old worker; escape control characters so one stays on one line."""
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode() for c in name)
