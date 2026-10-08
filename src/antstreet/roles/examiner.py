"""The examiner: checks the workers never see, written from the idea and the public names alone.

It is shown the investor's idea and the names the product must expose (file paths and the names
the term sheet's briefs state or its check files import), never a visible check's body:
independence from the checks the workers are graded on is the point. Its output is data until
`examine`'s gate has run: every quote a fragment of the idea, every file parsing and defining a
test, ids `h01`.. unique, and every check failing on an empty workspace. `run_examiner` books the
call, stores the checks in the run folder's `held_out/`, and tells the investor when it could not;
the run then goes on without held-out checks. The investor approves what is stored
(`approval.review_term_sheet`).
"""

from __future__ import annotations

import ast
import contextlib
import json
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from antstreet import budget, held_out
from antstreet.ledger import EventType, LedgerWriter
from antstreet.redact import safe_text
from antstreet.roles.advisory import _block
from antstreet.roles.base import RoleError, RoleOutputError, RoleSpec, call_role, ledger_fields
from antstreet.roles.stories import MIN_SOURCE_CHARS, is_fragment
from antstreet.rundir import Recorder, RunPaths
from antstreet.stream import Usage
from antstreet.termsheet import TermSheet
from antstreet.worker import CLI

MAX_CODE_CHARS = 20_000  # a held-out check is one behaviour; a file this long is not
MAX_NAMES = 60  # the public names shown to the model; a brief naming more is not a contract
_NAME = re.compile(r"`([A-Za-z_][\w.]{0,59}(?:\([\w\s,=*.:'\"\[\]|-]{0,60}\))?)`")
# Interfaces a brief states in prose: a call shape `name(args)` and a `*.py` file name.
_CALL = re.compile(r"\b[A-Za-z_]\w{0,59}\([\w\s,=*.:'\"\[\]|-]{0,60}\)")
_PY_FILE = re.compile(r"(?<![\w./-])(?:[\w-]{1,40}/){0,3}[\w-]{1,40}\.py\b")
_IMPORTED = re.compile(r"[A-Za-z_][\w.]{0,59}\Z")
_NOT_PRODUCT = frozenset(sys.stdlib_module_names) | {"pytest"}
_SHOWN_PROBLEMS = 10  # problems kept in the ledger event
_PROBLEM_CHARS = 300

EXAMINER = RoleSpec(
    name="examiner",
    department="quality",
    reports_to="boss",
    purpose="writes pytest checks from the idea and public names alone; run only on the product",
    gate=(
        "exactly the asked number of checks, each quote a fragment of the idea, every file "
        "parsing and defining a test, ids h01.. unique, every check failing on an empty workspace"
    ),
    prompt="examiner_v1.md",
    skills=(
        "examiner/import-public-names-only",
        "examiner/probe-the-skimmed-rules",
        "examiner/quote-the-rule",
    ),
)
SPECS = (EXAMINER,)


@dataclass(frozen=True, slots=True)
class PublicNames:
    files: tuple[str, ...]  # what the tasks own, and the `*.py` files their briefs name
    names: tuple[str, ...]  # modules and symbols the check files import, and code-quoted names in
    # the briefs; only names are taken from a visible check, never a line of its body


def public_names(sheet: TermSheet, checks_dir: Path) -> PublicNames:
    """The contract a held-out check may import against. A check file contributes the product
    modules and symbols it imports (an unparsable file contributes nothing); a task brief
    contributes the names it quotes in code, such as `reverse(s)`, and those it states in prose:
    a call shape `reverse(s)` and a file name `rev.py`. A test file is never a public name, so a
    brief that mentions a visible check's file does not show it. Nothing else leaves the files."""
    visible = {c.file for c in sheet.checks}
    files = dict.fromkeys(p for t in sheet.tasks for p in t.paths if p.strip() and p != ".")
    names: dict[str, None] = {}
    for task in sheet.tasks:
        prose = [m[0] for m in _CALL.finditer(task.brief)]
        stated = [m[0] for m in _PY_FILE.finditer(task.brief)]
        names.update(dict.fromkeys(_NAME.findall(task.brief) + prose))
        files.update(dict.fromkeys(f for f in stated if not _is_test(f, visible)))
    for check in sheet.checks:
        names.update(dict.fromkeys(_imported(checks_dir / check.file)))
    return PublicNames(
        tuple(files), tuple(n for n in names if not _is_test(n, visible))[:MAX_NAMES]
    )


def _is_test(name: str, visible: set[str]) -> bool:
    """Whether a stated name is a visible check's file or looks like a test."""
    base = name.rsplit("/", 1)[-1]
    return base in visible or base.startswith(("test_", "conftest")) or base.endswith("_test.py")


def _imported(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_bytes().decode("utf-8-sig"))
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
        return []
    found: list[str] = []
    for node in ast.walk(tree):  # names only: the body of the check never leaves this function
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] not in _NOT_PRODUCT:
                found += [node.module, *(a.name for a in node.names if a.name != "*")]
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.split(".")[0] not in _NOT_PRODUCT]
    return [name for name in found if _IMPORTED.match(name)]


def examiner_schema(n: int) -> dict[str, Any]:
    """Exactly `n` checks: the schema pins the count, the gate still checks it."""
    text = {"type": "string", "minLength": 1}
    return {
        "type": "object",
        "properties": {
            "checks": {
                "type": "array",
                "minItems": n,
                "maxItems": n,
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "source": text, "code": text},
                    "required": ["id", "source", "code"],
                },
            }
        },
        "required": ["checks"],
    }


def examine(
    idea: str,
    names: PublicNames,
    n: int,
    visible_ids: Sequence[str],
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    timeout_s: float = 300.0,
) -> tuple[list[tuple[held_out.HeldOutCheck, str]], Usage]:
    """One call: `n` held-out checks, each with its code. Nothing is written to the run.

    Raises ValueError before the call for a bad idea or count, RoleError when the call fails and
    RoleOutputError (with the refused output and the usage) when the output fails the gate; the
    caller books the spend either way.
    """
    if not idea.strip():
        raise ValueError("the examiner needs the idea")
    if type(n) is not int or not 1 <= n <= held_out.MAX_HELD_OUT:
        raise ValueError(f"n must be a whole number from 1 to {held_out.MAX_HELD_OUT}, got {n!r}")
    shown = "\n".join(
        [f"files: {', '.join(names.files) or '(none given)'}"]
        + [f"name: {name}" for name in names.names]
    )
    prompt = "\n\n".join(
        [
            f"Write exactly {n} held-out checks.",
            _block("The idea, in the investor's words:", idea.strip()),
            _block("The public names the product must expose:", shown),
        ]
    )
    output = call_role(
        EXAMINER,
        prompt,
        examiner_schema(n),
        env=env,
        model=model,
        executable=executable,
        timeout_s=timeout_s,
    )
    entries, problems = _parse(output.data, idea, n)
    if not problems:
        problems = _file_problems(entries, visible_ids)
    if problems:
        raise RoleOutputError(EXAMINER.name, problems, output.usage, output.data)
    return entries, output.usage


def _parse(
    data: Mapping[str, Any], idea: str, n: int
) -> tuple[list[tuple[held_out.HeldOutCheck, str]], list[str]]:
    """The checks in the output, and every problem that needs no file and no subprocess."""
    items = data.get("checks")
    if not isinstance(items, list):
        return [], ["checks is not a list"]
    problems: list[str] = [] if len(items) == n else [f"{len(items)} checks, asked for {n}"]
    entries: list[tuple[held_out.HeldOutCheck, str]] = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not all(
            isinstance(item.get(k), str) for k in ("id", "source", "code")
        ):
            problems.append(f"check {i}: needs a text id, source and code")
            continue
        check_id, source, code = item["id"], item["source"], item["code"]
        name = f"check {safe_text(check_id, limit=40)!r}"
        if not is_fragment(source, idea, min_chars=MIN_SOURCE_CHARS):
            problems.append(f"{name}: source must be a fragment of the idea, word for word")
        if not code.strip() or len(code) > MAX_CODE_CHARS:
            problems.append(f"{name}: code must be 1 to {MAX_CODE_CHARS} characters")
        entries.append(
            (held_out.HeldOutCheck(check_id, held_out.file_name(check_id), source), code)
        )
    problems += held_out.id_problems([c.id for c, _ in entries])
    return entries, problems


def _file_problems(
    entries: Sequence[tuple[held_out.HeldOutCheck, str]], visible_ids: Sequence[str]
) -> list[str]:
    """Write the candidates to a scratch folder and run the same gate the investor's edits meet:
    each file parses and defines a test, and each check fails on an empty workspace."""
    with tempfile.TemporaryDirectory(prefix="boss_examiner_") as scratch:
        held_out.write(Path(scratch), entries)
        return held_out.problems(Path(scratch), visible_ids)


def run_examiner(
    sheet: TermSheet,
    paths: RunPaths,
    ledger: LedgerWriter,
    run_id: str,
    *,
    n: int,
    env: Mapping[str, str],
    model: str,
    reserve_micros: int = budget.RESERVE_MICROS,
    executable: str = CLI,
    say: Callable[[str], None] = print,
) -> bool:
    """Call the examiner once for this run, between the boss's draft and the investor's approval.

    Writes the checks to `paths.held_out` and returns True, or returns False and tells the
    investor why; either way the call's spend is booked as a `role_call` under `role:examiner`
    in round 1, so it counts against that round's budget. A run whose examiner failed, was refused
    or was skipped for budget goes on without held-out checks.
    """
    events = paths.events()
    if any(e.event is EventType.ROLE_CALL and e.actor == EXAMINER.actor for e in events):
        return bool(held_out.hashes(paths.held_out))  # asked once per run, never twice
    record = Recorder(ledger, run_id, round=1)

    def book(usage: Usage, outcome: str, kept: int, problems: Sequence[str]) -> None:
        shown = [safe_text(p, limit=_PROBLEM_CHARS) for p in problems[:_SHOWN_PROBLEMS]]
        extra = {"requested": n, "kept": kept, "problems": shown}
        fields = ledger_fields(EXAMINER, usage, outcome, model=model, env=env, **extra)
        record(EXAMINER.actor, EventType.ROLE_CALL, **fields)

    room = budget.remaining(sheet, events, 1) - EXAMINER.cap_micros
    if room < budget.min_round_budget(reserve_micros):
        why = "round 1 could not then fund a worker slice"
        book(Usage(0, 0, 0, 0), "skipped", 0, [why])
        say(f"No held-out checks: the examiner's call could cost up to its cap and {why}.")
        return False
    try:
        entries, usage = examine(
            sheet.idea,
            public_names(sheet, paths.checks),
            n,
            [c.id for c in sheet.checks],
            env=env,
            model=model,
            executable=executable,
        )
    except RoleError as exc:
        problems = exc.problems if isinstance(exc, RoleOutputError) else [str(exc)]
        book(exc.usage, str(exc.outcome), 0, problems)  # the spend first: nothing below may lose it
        if isinstance(exc, RoleOutputError) and exc.data is not None:
            with contextlib.suppress(OSError):  # evidence, best effort
                paths.examiner_refused.write_text(json.dumps(exc.data, indent=2), encoding="utf-8")
        say(f"No held-out checks: the examiner's output was not usable ({problems[0]}).")
        return False
    try:
        held_out.write(paths.held_out, entries)
    except OSError as exc:
        shutil.rmtree(paths.held_out, ignore_errors=True)  # never a half-written folder
        book(usage, "completed", 0, [f"cannot write the held-out checks: {exc}"])
        say(f"No held-out checks: they could not be written ({exc}).")
        return False
    book(usage, "completed", len(entries), [])
    plural = "" if len(entries) == 1 else "s"
    say(f"The examiner wrote {len(entries)} held-out check{plural}. No worker will see them.")
    return True
