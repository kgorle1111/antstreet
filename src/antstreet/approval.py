"""Investor approval of a term sheet, recorded in the ledger and bound to the exact content.

The approval event carries hashes of the term sheet and every check file, and, when the run has
held-out checks, of everything in its `held_out/` folder. `require_approval` is called before
anything is spent, so an edit made after approval (by anyone, including a worker) voids it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from antstreet import context, held_out, signing, spec
from antstreet.dispatch import DispatchPolicy, DispatchView, render_table
from antstreet.ledger import Event, EventType, LedgerWriter
from antstreet.redact import _CONTROL_ESCAPES, safe_text
from antstreet.termsheet import TermSheet, TermSheetError, validate
from antstreet.worker import usd

TERM_SHEET_FILE = "term_sheet.json"
MAX_BRIEF_CHARS = 2_000  # shown cut (marked) beyond this; the hashed term sheet keeps all of it
MAX_DESCRIPTION_CHARS = 300
YES = ("y", "yes", "a", "approve")  # every investor question takes these as yes
NO = ("n", "no", "r", "reject")
Ask = Callable[[str], str]
Say = Callable[[str], None]


@dataclasses.dataclass(frozen=True, slots=True)
class SpecShown:
    """What the investor is shown about the rules: the view, and what the approval records."""

    text: str
    summary: dict[str, Any]


SpecView = Callable[[TermSheet], SpecShown]


def spec_view(
    rules_path: Path, checks_dir: Path, untested: Mapping[str, str] | None = None
) -> SpecView:
    """The investor's rule coverage view for a term sheet, recomputed from the files on disk each
    time it is asked for: the rule list is re-derived from the sheet's idea (a list edited to drop
    a rule is `spec.SpecError`), and the claims are the checks' own `criteria`. `untested` is the
    boss's waivers, rule id to reason."""
    waived = dict(untested or {})

    def view(sheet: TermSheet) -> SpecShown:
        split = spec.load(rules_path, sheet.idea)
        sources = {}
        for check in sheet.checks:
            try:
                sources[check.id] = (checks_dir / check.file).read_text(encoding="utf-8-sig")
            except (OSError, UnicodeDecodeError):
                continue  # reported as unreadable by verify
        claims = {c.id: c.criteria for c in sheet.checks}
        report = spec.verify(split, claims, sources, waived)
        if report.problems:  # a claim on a rule that does not exist is not a claim to approve
            problems = "; ".join(report.problems)
            raise spec.SpecError(f"the checks' rule citations are malformed: {problems}")
        summary = report.to_summary()
        summary["waived_reasons"] = {
            r: safe_text(" ".join(waived[r].split()), limit=MAX_DESCRIPTION_CHARS)
            for r in summary["waived"]
        }
        return SpecShown(spec.render_report(report, waived), summary)

    return view


class NotApprovedError(Exception):
    """No investor approval matches the current term sheet and check files."""


def content_hashes(
    sheet: TermSheet, checks_dir: Path, rules_path: Path | None = None
) -> dict[str, str]:
    """Hashes of what the investor approved. The approval flag itself is excluded. A run with a
    rule list (`rules_path` names a file that exists) hashes it too, under `rules.json`; a run
    without one has the hashes it always had, so an old approval still verifies."""
    unapproved = dataclasses.replace(sheet, approved_by_investor=False)
    hashes = {"term_sheet": hashlib.sha256(unapproved.to_json().encode()).hexdigest()}
    for check in sheet.checks:
        hashes[check.file] = hashlib.sha256((checks_dir / check.file).read_bytes()).hexdigest()
    if rules_path is not None and rules_path.is_file():
        hashes[spec.RULES_FILE] = hashlib.sha256(rules_path.read_bytes()).hexdigest()
    return hashes


def require_approval(
    events: Iterable[Event],
    sheet: TermSheet,
    checks_dir: Path,
    held_out_dir: Path | None = None,
    key_path: Path | None = None,
    rules_path: Path | None = None,
) -> None:
    """Raise NotApprovedError unless an investor approval matches the files on disk. With a
    `held_out_dir`, the approval must also match that folder exactly, so a held-out file edited,
    added or removed after approval voids it (an approval made without held-out checks records
    none, so a folder that appears later voids it too).

    With a `key_path` that holds the project's investor key, a signed approval must carry a valid
    HMAC, and an unsigned one counts only when it is older than the hash chain (its line has no
    `prev`): a line written by this code always signs, so an unsigned approval inside the chain
    is a forgery. Without a key file nothing can be verified and a signature is not required.

    A `rules_path` that exists must hold the rule list of the term sheet's idea (`spec.load`) and
    match the approval's `rules.json` hash: a rule dropped from it, before or after approval,
    voids the approval."""
    try:
        current = content_hashes(sheet, checks_dir, rules_path)
        if rules_path is not None and rules_path.is_file():
            spec.load(rules_path, sheet.idea)
        held = None if held_out_dir is None else held_out.hashes(held_out_dir)
        key = None if key_path is None else signing.load_key(key_path)
    except OSError as exc:  # a check deleted or made unreadable is a check that changed
        raise NotApprovedError(f"an approved check cannot be read: {exc}") from exc
    except (signing.SigningError, spec.SpecError) as exc:
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
    view: DispatchView | None = None,
    spec_shown: SpecView | None = None,
    rules_path: Path | None = None,
    fold: bool = False,
) -> TermSheet | None:
    """Show the term sheet; loop until the investor approves (returns the sheet) or rejects (None).

    The investor may edit term_sheet.json and the check files; edits are re-validated before the
    next decision. Only code sets `approved_by_investor`. `notes` are the specialist roles'
    opinions on the draft (stories, coverage, an audit): they are shown under the sheet and bind
    nothing. Approval is of the sheet and the checks alone, and of the held-out checks when
    `held_out_dir` holds any: the investor reads them with the rest, and their hashes go into the
    same approval event. The ledger writer signs the investor's events (`LedgerWriter`).

    With a `view` (`--dispatch rules`) the sheet shows its route and the dispatch table, the
    investor may edit both in term_sheet.json, and an edit is held to the view's policy. The
    approval then records the route it was given on.

    With `spec_shown` the rule coverage (uncovered rules first) is printed above the term sheet and
    is part of what the investor must have seen: it is recomputed before an approval, and a change
    since it was shown means "review it again". A rule list that is not the idea's (`SpecError`)
    cannot be approved. The approval then records the coverage summary and hashes the rule list at
    `rules_path` with the rest.

    With `fold` each check is shown as one line (its description, file and SHA-256) instead of its
    code, and `v` prints everything in full. The approval still binds the full text: a change to
    any check since it was shown means "review it again", folded or not.
    """
    policy = None if view is None else view.policy
    path = run_dir / TERM_SHEET_FILE
    path.write_text(dataclasses.replace(sheet, approved_by_investor=False).to_json())
    while True:
        try:
            coverage = spec_shown(sheet) if spec_shown else None
            spec_problem = None
        except spec.SpecError as exc:
            coverage, spec_problem = None, str(exc)
        shown = (coverage.text + "\n\n" if coverage else "") + render(
            sheet, checks_dir, held_out_dir, view
        )
        if spec_problem:
            say(f"The rule list cannot be used: {spec_problem}")
        if fold:
            folded = render(sheet, checks_dir, held_out_dir, view, fold=True)
            say((coverage.text + "\n\n" if coverage else "") + folded)
        else:
            say(shown)
        for note in notes:
            say(note)
        question = "[a]pprove, [r]eject, [e]dit files and re-check"
        question += ", or [v]iew every check in full? " if fold else "? "
        try:
            answer = ask(question).strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "r"
        while fold and answer in ("v", "view"):
            say(shown)
            try:
                answer = ask("[a]pprove, [r]eject, or [e]dit files and re-check? ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = "r"
        if answer in YES:
            if spec_problem:
                say(
                    f"Not approved: the rule list is not the idea's ({spec_problem}). "
                    "Reject, or edit and re-check."
                )
                continue
            # Approval binds to what is on disk now, and only if the investor has seen exactly that.
            try:
                current, now, again = pending(path, checks_dir, held_out_dir, view, spec_shown)
            except TermSheetError as exc:
                say(_problems_text("The term sheet does not validate", exc))
                continue
            except spec.SpecError as exc:
                say(f"Not approved: the rule list cannot be used: {exc}")
                continue
            if again != shown:
                say("The term sheet or a check changed since it was shown; review it again.")
                sheet = current
                continue
            return _approve(
                current,
                path,
                checks_dir,
                ledger,
                run_id,
                now,
                held_out_dir,
                policy,
                rules_path,
                routed=_routed(view),
            )
        if answer in NO:
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
            sheet = _reload_after_edit(sheet, path, checks_dir, held_out_dir, ask, say, policy)
            continue
        say(f"Unrecognised answer {answer!r}.")


def pending(
    path: Path,
    checks_dir: Path,
    held_out_dir: Path | None,
    view: DispatchView | None,
    spec_shown: SpecView | None,
) -> tuple[TermSheet, SpecShown | None, str]:
    """The term sheet on disk (validated, never approved), its rule coverage, and exactly the text
    an investor approving it must have read. TermSheetError or `spec.SpecError` when it cannot be
    approved as it stands."""
    current = _load_valid(path, checks_dir, held_out_dir, None if view is None else view.policy)
    now = spec_shown(current) if spec_shown else None
    text = (now.text + "\n\n" if now else "") + render(current, checks_dir, held_out_dir, view)
    return current, now, text


def shown_digest(text: str) -> str:
    """What `boss approve --sheet` takes: short enough to type, and it names one shown text."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def approve_shown(
    digest: str,
    run_dir: Path,
    checks_dir: Path,
    ledger: LedgerWriter,
    run_id: str,
    *,
    held_out_dir: Path | None = None,
    view: DispatchView | None = None,
    spec_shown: SpecView | None = None,
    rules_path: Path | None = None,
) -> TermSheet:
    """The investor's approval of a sheet read earlier, outside any question (`boss approve`).
    `digest` is the `shown_digest` of the text they read; anything changed since then is a
    different text, so NotApprovedError, and nothing is written. TermSheetError or
    `spec.SpecError` when the sheet on disk cannot be approved at all."""
    path = run_dir / TERM_SHEET_FILE
    current, now, text = pending(path, checks_dir, held_out_dir, view, spec_shown)
    if not hmac.compare_digest(shown_digest(text), digest.strip().lower()):
        raise NotApprovedError(
            "the term sheet or a check is not the one shown with that --sheet value (it changed "
            "since, or the value was mistyped); read it again and approve what is there now"
        )
    shown = hashlib.sha256(text.encode()).hexdigest()
    policy = None if view is None else view.policy
    return _approve(
        current,
        path,
        checks_dir,
        ledger,
        run_id,
        now,
        held_out_dir,
        policy,
        rules_path,
        shown,
        routed=_routed(view),
    )


def _approve(
    current: TermSheet,
    path: Path,
    checks_dir: Path,
    ledger: LedgerWriter,
    run_id: str,
    now: SpecShown | None,
    held_out_dir: Path | None,
    policy: DispatchPolicy | None,
    rules_path: Path | None,
    shown_sha256: str | None = None,
    *,
    routed: dict[str, Any] | None = None,
) -> TermSheet:
    approved = dataclasses.replace(current, approved_by_investor=True)
    path.write_text(approved.to_json())
    data: dict[str, Any] = {"hashes": content_hashes(approved, checks_dir, rules_path)}
    if now is not None:
        data["spec"] = now.summary
    if held_out_dir is not None and (held := held_out.hashes(held_out_dir)):
        data["held_out_hashes"] = held
    if policy is not None:
        data["route"] = approved.route
    if shown_sha256 is not None:
        data["shown_sha256"] = shown_sha256
    if routed:
        data["routed"] = routed
    ledger.append(Event(run=run_id, round=0, actor="investor", event=EventType.APPROVED, data=data))
    return approved


def _routed(view: DispatchView | None) -> dict[str, Any] | None:
    """The cascade's start for each task, as the approval records it."""
    if view is None or not view.routing:
        return None
    return {k: dict(v) for k, v in view.routing.items()}


def _reload_after_edit(
    sheet: TermSheet,
    path: Path,
    checks_dir: Path,
    held_out_dir: Path | None,
    ask: Ask,
    say: Say,
    policy: DispatchPolicy | None,
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
            return _load_valid(path, checks_dir, held_out_dir, policy)
        except TermSheetError as exc:
            say(_problems_text("The edited term sheet does not validate", exc))
            try:
                ask("Fix the files, then press Enter to re-check. ")
            except (EOFError, KeyboardInterrupt):
                return sheet


def _load_valid(
    path: Path, checks_dir: Path, held_out_dir: Path | None, policy: DispatchPolicy | None
) -> TermSheet:
    """The term sheet as it is on disk, never approved, or TermSheetError. Held-out files are
    held to the same gate as when the examiner wrote them (an edit cannot break it)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TermSheetError([f"cannot read {path}: {exc}"]) from exc
    sheet = dataclasses.replace(TermSheet.from_json(text), approved_by_investor=False)
    validate(sheet, checks_dir, policy)
    if held_out_dir is not None and (
        found := held_out.problems(held_out_dir, {c.id for c in sheet.checks})
    ):
        raise TermSheetError(found)
    return sheet


def _problems_text(headline: str, exc: TermSheetError) -> str:
    return f"{headline}:\n" + "\n".join(f"  - {p}" for p in exc.problems)


def render(
    sheet: TermSheet,
    checks_dir: Path,
    held_out_dir: Path | None = None,
    view: DispatchView | None = None,
    *,
    fold: bool = False,
) -> str:
    """The term sheet as the investor reads it. `fold` shows each check as one line with its
    file's SHA-256 instead of its code."""
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
    if view is not None:
        sizes = {t.id: context.first_context_chars(sheet, t, checks_dir) for t in sheet.tasks}
        lines += ["", *render_table(sheet, dataclasses.replace(view, contexts=sizes))]
    for check in sheet.checks:
        head = f"Check {check.id} [{check.task}] {_line(check.description, MAX_DESCRIPTION_CHARS)}"
        if fold:
            lines.append(f"{head} ({check.file} {_digest(checks_dir / check.file)})")
            continue
        lines += [
            f"\n{head}",
            f"--- {checks_dir / check.file}",
            _check_text(checks_dir / check.file),
        ]
    if fold:
        lines.insert(len(lines) - len(sheet.checks), "\nCHECKS (folded; [v]iew shows the code)")
        return "\n".join(lines + _held_out_lines(held_out_dir, fold=True))
    return "\n".join(lines + _held_out_lines(held_out_dir))


def _digest(path: Path) -> str:
    try:
        return "sha256 " + hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError as exc:
        return f"<unreadable: {exc}>"


def _held_out_lines(held_out_dir: Path | None, *, fold: bool = False) -> list[str]:
    """The held-out checks in full, marked as the ones no worker will be shown."""
    try:
        checks = held_out.load(held_out_dir) if held_out_dir is not None else []
    except held_out.HeldOutError as exc:
        return ["", f"HELD-OUT CHECKS cannot be shown: {exc}"]
    if held_out_dir is None or not checks:
        return []
    lines = ["", "HELD-OUT CHECKS (graded on the finished product only; workers never see them)"]
    for check in checks:
        if fold:
            what = _line(check.source, MAX_DESCRIPTION_CHARS)
            lines.append(f"Held-out check {check.id} verifies: {what} ({check.file} "
                         f"{_digest(held_out_dir / check.file)})")  # fmt: skip
            continue
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
