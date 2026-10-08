"""What a worker is told: its first brief, and what the gate found after each slice."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from pathlib import Path

from antstreet import handoff
from antstreet.gate import CheckResult
from antstreet.ledger import Event
from antstreet.redact import redact, safe_text
from antstreet.rule import Decision, SliceRecord, Verdict
from antstreet.termsheet import Task, TermSheet

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
    parts += check_sections(sheet, [c.id for c in sheet.checks if c.task == task.id], checks_dir)
    parts.append("When you stop, report your status.")
    return "\n\n".join(parts)


def check_sections(sheet: TermSheet, check_ids: Collection[str], checks_dir: Path) -> list[str]:
    """One section per named check, in the sheet's order: its id, file, description and code."""
    sections = []
    for check in sheet.checks:
        if check.id in check_ids:
            code = (checks_dir / check.file).read_text(encoding="utf-8").rstrip()
            sections.append(f"--- check {check.id} ({check.file}): {check.description}\n{code}")
    return sections


def added_checks_note(sheet: TermSheet, check_ids: Collection[str], checks_dir: Path) -> str:
    """What a worker is told when the investor approved more checks after it last worked: it
    has never seen their code, and the gate will run them."""
    sections = check_sections(sheet, check_ids, checks_dir)
    return "\n\n".join(
        [
            "The investor approved more checks after reviewing the work. They must pass too.",
            *sections,
        ]
    )


def _fenced(text: str) -> str:
    """Quote text so its own lines cannot be mistaken for the brief around it."""
    return "\n".join(f"> {line}".rstrip() for line in text.strip().splitlines())


def continuation_prompt(
    results: Sequence[CheckResult],
    disputed: Collection[str] = (),
    denied_tools: Sequence[str] = (),
    example_path: str = "module.py",
    investor_notes: Sequence[str] = (),
    denial_reasons: Sequence[Mapping[str, str]] = (),
) -> str:
    """The brief for a later slice: which checks pass now, the gate's output for the rest, which
    of the failing ones this worker has already disputed, and what to do about refused tool
    calls, with the reason the CLI gave for each (a worker whose call is refused tends to give up
    as "blocked"). `denial_reasons` holds cleaned, bounded text: see rundir.denial_reasons."""
    passing = sorted(r.check_id for r in results if r.passed)
    parts = [
        "Continue your task. After your last slice the gate ran your checks.",
        f"Passing: {', '.join(passing) if passing else 'none'}",
    ]
    for r in results:
        if not r.passed:
            tail = redact(r.output_tail[-FEEDBACK_TAIL_CHARS:]).strip()
            parts.append(f"Failing: {r.check_id} ({r.detail})\n{tail}")
    parts += investor_notes  # the investor's own words and rulings, ahead of the rest
    open_disputes = sorted(set(disputed) - set(passing))
    if open_disputes:
        parts.append(
            f"You disputed: {', '.join(open_disputes)}. The investor will rule on those; "
            "do not bend your code to them."
        )
    if denied_tools:
        if denial_reasons:
            lines = (f'- {r["tool"]}: "{r["reason"]}"' for r in denial_reasons)
            refused = "these tool calls were refused, for the reasons the CLI gave:\n" + "\n".join(
                lines
            )
        else:
            refused = f"your {', '.join(denied_tools)} calls were refused."
        parts.append(
            f"In your last slice {refused}\nRead, Write and Edit work on files inside your "
            "current folder, which is your whole workspace; nothing else is available. "
            f"Use relative paths, for example `{example_path}`, and do the work again."
        )
    # The decision to bend or dispute is made here, against a failing check: in a live run a
    # worker that wrote "the test contradicts the request" in its reason still chased the check.
    parts.append(
        "Fix what is failing. If a failing check contradicts the request, do not change correct "
        "code for it: keep your code and list the check under `disputed_checks`. "
        "When you stop, report your status."
    )
    return "\n\n".join(parts)


def predecessor_disputes_note(disputes: Mapping[str, str]) -> str:
    """The checks a fired worker called wrong that the investor has not ruled on, with its
    reasons. Quoted claims, not instructions: nobody has verified them."""
    lines = [f'- {check}: "{safe_text(reason, limit=300)}"' for check, reason in disputes.items()]
    return "\n".join(
        [
            "Your predecessor disputed these checks as wrong. The quotes are its claims, not "
            "verified, and the investor has not ruled on them:",
            *lines,
        ]
    )


def reassignment_brief(
    prompt: str,
    *,
    fired: Event,
    history: Sequence[SliceRecord],
    gate_results: Sequence[CheckResult],
    kept: Path,
    with_files: bool = True,
    with_tails: bool = True,
) -> str:
    """The first brief for a replacement worker: the task, why its predecessor was stopped, and
    the predecessor's files, offered under `previous_attempt/` but not imposed. The file list and
    the gate output in the notes can be left out (the context bundle does when over its bound)."""
    verdict = Verdict(Decision.FIRE, fired.data["reason"], fired.data.get("evidence", {}))
    tails = {} if with_tails else {"tail_chars": 0}
    notes = handoff.failure_notes(
        verdict, history, gate_results, fired.data.get("last_reason"), **tails
    )
    files = [p.relative_to(kept).as_posix() for p in sorted(kept.rglob("*")) if p.is_file()]
    files = files if with_files else []
    return handoff.reassignment_prompt(prompt, notes, files)
