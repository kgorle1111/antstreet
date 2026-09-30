"""Investor approval of a term sheet, recorded in the ledger and bound to the exact content.

The approval event carries hashes of the term sheet and every check file. `require_approval` is
called before anything is spent, so an edit made after approval (by anyone, including a worker)
voids it.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from boss.ledger import Event, EventType, LedgerWriter
from boss.redact import _CONTROL_ESCAPES, safe_text
from boss.termsheet import TermSheet, TermSheetError, validate
from boss.worker import usd

TERM_SHEET_FILE = "term_sheet.json"
MAX_BRIEF_CHARS = 2_000  # shown cut (marked) beyond this; the hashed term sheet keeps all of it
MAX_DESCRIPTION_CHARS = 300
Ask = Callable[[str], str]
Say = Callable[[str], None]


class NotApprovedError(Exception):
    """No investor approval matches the current term sheet and check files."""


def content_hashes(sheet: TermSheet, checks_dir: Path) -> dict[str, str]:
    """Hashes of what the investor approved. The approval flag itself is excluded."""
    unapproved = dataclasses.replace(sheet, approved_by_investor=False)
    hashes = {"term_sheet": hashlib.sha256(unapproved.to_json().encode()).hexdigest()}
    for check in sheet.checks:
        hashes[check.file] = hashlib.sha256((checks_dir / check.file).read_bytes()).hexdigest()
    return hashes


def require_approval(events: Iterable[Event], sheet: TermSheet, checks_dir: Path) -> None:
    try:
        current = content_hashes(sheet, checks_dir)
    except OSError as exc:  # a check deleted or made unreadable is a check that changed
        raise NotApprovedError(f"an approved check cannot be read: {exc}") from exc
    for event in events:
        if (
            event.event is EventType.APPROVED
            and event.actor == "investor"
            and event.data.get("hashes") == current
        ):
            return
    raise NotApprovedError("the term sheet or its checks have no matching investor approval")


def review_term_sheet(
    sheet: TermSheet,
    checks_dir: Path,
    run_dir: Path,
    ledger: LedgerWriter,
    run_id: str,
    *,
    ask: Ask = input,
    say: Say = print,
    notes: Sequence[str] = (),
) -> TermSheet | None:
    """Show the term sheet; loop until the investor approves (returns the sheet) or rejects (None).

    The investor may edit term_sheet.json and the check files; edits are re-validated before the
    next decision. Only code sets `approved_by_investor`. `notes` are the specialist roles'
    opinions on the draft (stories, coverage, an audit): they are shown under the sheet and bind
    nothing. Approval is of the sheet and the checks alone.
    """
    path = run_dir / TERM_SHEET_FILE
    path.write_text(dataclasses.replace(sheet, approved_by_investor=False).to_json())
    while True:
        shown = render(sheet, checks_dir)
        say(shown)
        for note in notes:
            say(note)
        try:
            answer = ask("[a]pprove, [r]eject, or [e]dit files and re-check? ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "r"
        if answer in ("a", "approve"):
            # Approval binds to what is on disk now, and only if the investor has seen exactly that.
            try:
                current = _load_valid(path, checks_dir)
            except TermSheetError as exc:
                say(_problems_text("The term sheet does not validate", exc))
                continue
            if render(current, checks_dir) != shown:
                say("The term sheet or a check changed since it was shown; review it again.")
                sheet = current
                continue
            approved = dataclasses.replace(current, approved_by_investor=True)
            path.write_text(approved.to_json())
            ledger.append(
                Event(
                    run=run_id,
                    round=0,
                    actor="investor",
                    event=EventType.APPROVED,
                    data={"hashes": content_hashes(approved, checks_dir)},
                )
            )
            return approved
        if answer in ("r", "reject"):
            ledger.append(
                Event(
                    run=run_id,
                    round=0,
                    actor="investor",
                    event=EventType.STOPPED,
                    data={"reason": "term sheet rejected"},
                )
            )
            # An investor edit may have set the flag; only an approval is allowed to leave it set.
            path.write_text(dataclasses.replace(sheet, approved_by_investor=False).to_json())
            say("Rejected. Nothing was funded.")
            return None
        if answer in ("e", "edit"):
            sheet = _reload_after_edit(sheet, path, checks_dir, ask, say)
            continue
        say(f"Unrecognised answer {answer!r}.")


def _reload_after_edit(
    sheet: TermSheet, path: Path, checks_dir: Path, ask: Ask, say: Say
) -> TermSheet:
    say(f"Edit {path} and the files in {checks_dir}, then press Enter.")
    try:
        ask("")
    except (EOFError, KeyboardInterrupt):
        return sheet
    while True:
        try:
            return _load_valid(path, checks_dir)
        except TermSheetError as exc:
            say(_problems_text("The edited term sheet does not validate", exc))
            try:
                ask("Fix the files, then press Enter to re-check. ")
            except (EOFError, KeyboardInterrupt):
                return sheet


def _load_valid(path: Path, checks_dir: Path) -> TermSheet:
    """The term sheet as it is on disk, never approved, or TermSheetError."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TermSheetError([f"cannot read {path}: {exc}"]) from exc
    sheet = dataclasses.replace(TermSheet.from_json(text), approved_by_investor=False)
    validate(sheet, checks_dir)
    return sheet


def _problems_text(headline: str, exc: TermSheetError) -> str:
    return f"{headline}:\n" + "\n".join(f"  - {p}" for p in exc.problems)


def render(sheet: TermSheet, checks_dir: Path) -> str:
    lines = [
        "TERM SHEET",
        f"Idea: {sheet.idea}",
        f"Budget: ${usd(sheet.budget_micros)} (estimated cost, not a bill)",
    ]
    for r in sheet.rounds:
        lines.append(
            f"Round {r.n}: ${usd(r.budget_micros)}, next unlocks at {r.unlock_checks} "
            f"passing checks"
        )
    for task in sheet.tasks:
        lines += [
            f"\nTask {task.id} (owns {', '.join(task.paths)}):",
            f"  {_line(task.brief, MAX_BRIEF_CHARS)}",
        ]
    for check in sheet.checks:
        code = _check_text(checks_dir / check.file)
        lines += [
            f"\nCheck {check.id} [{check.task}] {_line(check.description, MAX_DESCRIPTION_CHARS)}",
            f"--- {checks_dir / check.file}",
            code,
        ]
    return "\n".join(lines)


def _line(text: str, limit: int) -> str:
    """Boss-written text for a one-line slot: no forged lines, secrets masked, controls visible."""
    return safe_text(" ".join(text.split()), limit=limit)


def _check_text(path: Path) -> str:
    """Display text only; the gate, not this, decides what a check means.

    Never redacted or cut: the investor must read exactly what will run. Only control and
    invisible format characters are made visible (a raw ESC could rewrite the screen, a bidi
    override could reorder what is read); newlines and tabs stay.
    """
    try:
        text = path.read_bytes().decode("utf-8-sig", errors="replace").rstrip()
    except OSError as exc:
        return f"<unreadable: {exc}>"
    return text.translate(_CONTROL_ESCAPES)
