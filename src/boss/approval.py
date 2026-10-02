"""Investor approval of a term sheet, recorded in the ledger and bound to the exact content.

The approval event carries hashes of the term sheet and every check file, and, when the run has
held-out checks, of everything in its `held_out/` folder. `require_approval` is called before
anything is spent, so an edit made after approval (by anyone, including a worker) voids it.
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from boss import held_out, signing
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


def require_approval(
    events: Iterable[Event],
    sheet: TermSheet,
    checks_dir: Path,
    held_out_dir: Path | None = None,
    key_path: Path | None = None,
) -> None:
    """Raise NotApprovedError unless an investor approval matches the files on disk. With a
    `held_out_dir`, the approval must also match that folder exactly, so a held-out file edited,
    added or removed after approval voids it (an approval made without held-out checks records
    none, so a folder that appears later voids it too).

    With a `key_path` that holds the project's investor key, a signed approval must carry a valid
    HMAC, and an unsigned one counts only when it is older than the hash chain (its line has no
    `prev`): a line written by this code always signs, so an unsigned approval inside the chain
    is a forgery. Without a key file nothing can be verified and a signature is not required."""
    try:
        current = content_hashes(sheet, checks_dir)
        held = None if held_out_dir is None else held_out.hashes(held_out_dir)
        key = None if key_path is None else signing.load_key(key_path)
    except OSError as exc:  # a check deleted or made unreadable is a check that changed
        raise NotApprovedError(f"an approved check cannot be read: {exc}") from exc
    except signing.SigningError as exc:
        raise NotApprovedError(str(exc)) from exc
    unverified = False
    for event in events:
        if (
            event.event is EventType.APPROVED
            and event.actor == "investor"
            and event.data.get("hashes") == current
            and (held is None or event.data.get("held_out_hashes", {}) == held)
        ):
            if _signature_ok(event, key):
                return
            unverified = True
    if unverified:
        raise NotApprovedError(
            "an investor approval matches the term sheet and its checks but its signature does "
            "not verify against .boss/investor.key (forged, edited, or the key was replaced)"
        )
    raise NotApprovedError("the term sheet or its checks have no matching investor approval")


def _signature_ok(event: Event, key: bytes | None) -> bool:
    if signing.SIG_KEY in event.data:
        return key is not None and signing.verify(key, event)
    return key is None or event.prev is None


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
    held_out_dir: Path | None = None,
    key_path: Path | None = None,
) -> TermSheet | None:
    """Show the term sheet; loop until the investor approves (returns the sheet) or rejects (None).

    The investor may edit term_sheet.json and the check files; edits are re-validated before the
    next decision. Only code sets `approved_by_investor`. `notes` are the specialist roles'
    opinions on the draft (stories, coverage, an audit): they are shown under the sheet and bind
    nothing. Approval is of the sheet and the checks alone, and of the held-out checks when
    `held_out_dir` holds any: the investor reads them with the rest, and their hashes go into the
    same approval event. With a `key_path` the approval event is signed with the project's
    investor key, which is created there on first use.
    """
    path = run_dir / TERM_SHEET_FILE
    path.write_text(dataclasses.replace(sheet, approved_by_investor=False).to_json())
    while True:
        shown = render(sheet, checks_dir, held_out_dir)
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
                current = _load_valid(path, checks_dir, held_out_dir)
            except TermSheetError as exc:
                say(_problems_text("The term sheet does not validate", exc))
                continue
            if render(current, checks_dir, held_out_dir) != shown:
                say("The term sheet or a check changed since it was shown; review it again.")
                sheet = current
                continue
            approved = dataclasses.replace(current, approved_by_investor=True)
            path.write_text(approved.to_json())
            data: dict[str, Any] = {"hashes": content_hashes(approved, checks_dir)}
            if held_out_dir is not None and (held := held_out.hashes(held_out_dir)):
                data["held_out_hashes"] = held
            if key_path is not None:
                data = signing.signed(signing.load_or_create_key(key_path), run_id, 0, data)
            ledger.append(
                Event(run=run_id, round=0, actor="investor", event=EventType.APPROVED, data=data)
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
            sheet = _reload_after_edit(sheet, path, checks_dir, held_out_dir, ask, say)
            continue
        say(f"Unrecognised answer {answer!r}.")


def _reload_after_edit(
    sheet: TermSheet, path: Path, checks_dir: Path, held_out_dir: Path | None, ask: Ask, say: Say
) -> TermSheet:
    has_held_out = held_out_dir is not None and bool(held_out.hashes(held_out_dir))
    folders = f"{checks_dir} and {held_out_dir}" if has_held_out else f"{checks_dir}"
    say(f"Edit {path} and the files in {folders}, then press Enter.")
    try:
        ask("")
    except (EOFError, KeyboardInterrupt):
        return sheet
    while True:
        try:
            return _load_valid(path, checks_dir, held_out_dir)
        except TermSheetError as exc:
            say(_problems_text("The edited term sheet does not validate", exc))
            try:
                ask("Fix the files, then press Enter to re-check. ")
            except (EOFError, KeyboardInterrupt):
                return sheet


def _load_valid(path: Path, checks_dir: Path, held_out_dir: Path | None) -> TermSheet:
    """The term sheet as it is on disk, never approved, or TermSheetError. Held-out files are
    held to the same gate as when the examiner wrote them (an edit cannot break it)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TermSheetError([f"cannot read {path}: {exc}"]) from exc
    sheet = dataclasses.replace(TermSheet.from_json(text), approved_by_investor=False)
    validate(sheet, checks_dir)
    if held_out_dir is not None and (
        found := held_out.problems(held_out_dir, {c.id for c in sheet.checks})
    ):
        raise TermSheetError(found)
    return sheet


def _problems_text(headline: str, exc: TermSheetError) -> str:
    return f"{headline}:\n" + "\n".join(f"  - {p}" for p in exc.problems)


def render(sheet: TermSheet, checks_dir: Path, held_out_dir: Path | None = None) -> str:
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
    return "\n".join(lines + _held_out_lines(held_out_dir))


def _held_out_lines(held_out_dir: Path | None) -> list[str]:
    """The held-out checks in full, marked as the ones no worker will be shown."""
    try:
        checks = held_out.load(held_out_dir) if held_out_dir is not None else []
    except held_out.HeldOutError as exc:
        return ["", f"HELD-OUT CHECKS cannot be shown: {exc}"]
    if held_out_dir is None or not checks:
        return []
    lines = ["", "HELD-OUT CHECKS (graded on the finished product only; workers never see them)"]
    for check in checks:
        lines += [
            f"\nHeld-out check {check.id} verifies: {_line(check.source, MAX_DESCRIPTION_CHARS)}",
            f"--- {held_out_dir / check.file}",
            _check_text(held_out_dir / check.file),
        ]
    return lines


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
