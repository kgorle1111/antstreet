"""What a worker is told: its first brief, and what the gate found after each slice."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from pathlib import Path

from boss import handoff
from boss.gate import CheckResult
from boss.ledger import Event
from boss.redact import redact
from boss.rule import Decision, SliceRecord, Verdict
from boss.termsheet import Task, TermSheet

FEEDBACK_TAIL_CHARS = 1_200


def task_prompt(sheet: TermSheet, task: Task, checks_dir: Path) -> str:
    """The first brief: the investor's idea word for word, then the boss's reading of it (the
    task, the files it owns, and every check that task will face).

    The idea comes first and is named the source of truth because the boss's brief is a lossy
    paraphrase: in the pilot, workers given only the brief followed it where it dropped a rule.
    """
    parts = [
        "The investor asked for this. It is the source of truth; it is quoted word for word:\n"
        f"{_fenced(sheet.idea)}",
        f"Your task ({task.id}), as the boss wrote it: {task.brief}",
        f"Files you own: {', '.join(task.paths)}",
        "After you stop, an independent gate runs these checks against your files. "
        "You cannot run them yourself.",
    ]
    for check in sheet.checks:
        if check.task == task.id:
            code = (checks_dir / check.file).read_text(encoding="utf-8").rstrip()
            parts.append(f"--- check {check.id} ({check.file}): {check.description}\n{code}")
    parts.append("When you stop, report your status.")
    return "\n\n".join(parts)


def _fenced(text: str) -> str:
    """Quote text so its own lines cannot be mistaken for the brief around it."""
    return "\n".join(f"> {line}".rstrip() for line in text.strip().splitlines())


def continuation_prompt(results: Sequence[CheckResult], disputed: Collection[str] = ()) -> str:
    """The brief for a later slice: which checks pass now, the gate's output for the rest, and
    which of the failing ones this worker has already disputed."""
    passing = sorted(r.check_id for r in results if r.passed)
    parts = [
        "Continue your task. After your last slice the gate ran your checks.",
        f"Passing: {', '.join(passing) if passing else 'none'}",
    ]
    for r in results:
        if not r.passed:
            tail = redact(r.output_tail[-FEEDBACK_TAIL_CHARS:]).strip()
            parts.append(f"Failing: {r.check_id} ({r.detail})\n{tail}")
    open_disputes = sorted(set(disputed) - set(passing))
    if open_disputes:
        parts.append(
            f"You disputed: {', '.join(open_disputes)}. The investor will rule on those; "
            "do not bend your code to them."
        )
    parts.append("Fix what is failing. When you stop, report your status.")
    return "\n\n".join(parts)


def reassignment_brief(
    prompt: str,
    *,
    fired: Event,
    history: Sequence[SliceRecord],
    gate_results: Sequence[CheckResult],
    kept: Path,
) -> str:
    """The first brief for a replacement worker: the task, why its predecessor was stopped, and
    the predecessor's files, offered under `previous_attempt/` but not imposed."""
    verdict = Verdict(Decision.FIRE, fired.data["reason"], fired.data.get("evidence", {}))
    notes = handoff.failure_notes(verdict, history, gate_results, fired.data.get("last_reason"))
    files = [p.relative_to(kept).as_posix() for p in sorted(kept.rglob("*")) if p.is_file()]
    return handoff.reassignment_prompt(prompt, notes, files)
