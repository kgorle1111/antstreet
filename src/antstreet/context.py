"""The context bundle: everything one worker slice is told, bounded, named and hashed.

It wraps `briefs.py` and adds nothing a worker could not already have: the idea, the boss's brief,
the task's own checks, the gate's feedback and the investor's words, plus one new optional section,
the names other tasks must provide to this task's checks. It never reads another task's check
code, the held-out folder, a hidden benchmark check or anything under `.boss/`: the only files it
opens are the task's own check files, through `briefs`.

The bound is on the user prompt. The parts that make the brief a brief are never cut; the optional
ones are left out whole, in a fixed order, until it fits; if the mandatory ones alone are over, the
slice is refused before it is paid for.
"""

from __future__ import annotations

import ast
import hashlib
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from antstreet import briefs
from antstreet.gate import CheckResult
from antstreet.ledger import Event, EventType
from antstreet.redact import safe_text
from antstreet.rundir import RunPaths
from antstreet.termsheet import Task, TermSheet

MAX_BUNDLE_CHARS = 30_000  # about 7,500 tokens; kn: one number, tune it from `context_chars`
_MAX_NAMES_PER_FILE = 40
_PART_SEP = "\n\n"


class BundleTooBig(Exception):
    """The parts a brief cannot do without are over the bound. Raised before anything is spent."""

    def __init__(self, task: str, parts: Mapping[str, int], bound: int) -> None:
        sizes = ", ".join(f"{name} {n}" for name, n in parts.items())
        super().__init__(
            f"the brief for task {task} is {sum(parts.values())} characters ({sizes}) even with "
            f"every optional part left out; the limit is {bound}. Shorten the idea, the task or "
            "its checks."
        )


@dataclass(frozen=True, slots=True)
class Levels:
    """Which optional parts are in. `DROP_ORDER` goes from everything to the mandatory parts."""

    interfaces: bool
    files: bool  # the predecessor's file list
    tails: bool  # the older gate output in the failure notes


DROP_ORDER = (
    Levels(True, True, True),
    Levels(False, True, True),
    Levels(False, False, True),
    Levels(False, False, False),
)


@dataclass(frozen=True, slots=True)
class Handoff:
    """What a replacement is given about its predecessor (`briefs.reassignment_brief`)."""

    fired: Event
    history: Sequence[Any]
    gate_results: Sequence[CheckResult]
    kept: Path


@dataclass(frozen=True, slots=True)
class SliceInputs:
    """What the firm has worked out for one slice; the bundle only arranges it."""

    notes: Sequence[str] = ()
    resume: bool = False
    # a resumed slice
    gate_results: Sequence[CheckResult] = ()
    disputed: Collection[str] = ()
    denied_tools: Sequence[str] = ()
    denial_reasons: Sequence[Mapping[str, str]] = ()
    # the first slice of a replacement
    handoff: Handoff | None = None


@dataclass(frozen=True, slots=True)
class Bundle:
    system: str
    prompt: str
    parts: dict[str, int]  # characters of each part that is in
    dropped: tuple[str, ...]  # optional parts left out to fit the bound

    @property
    def sha256(self) -> str:
        return bundle_hash(self.system, self.prompt)

    def start_data(self) -> dict[str, Any]:
        """The keys a `slice_start` records so the exact text can be checked later."""
        return {
            "context_sha256": self.sha256,
            "context_chars": len(self.prompt),
            "context_parts": dict(self.parts),
        }

    def file_bytes(self) -> bytes:
        return _file_bytes(self.system, self.prompt)


def _file_bytes(system: str, prompt: str) -> bytes:
    return system.encode("utf-8") + b"\0" + prompt.encode("utf-8")


def bundle_hash(system: str, prompt: str) -> str:
    """SHA-256 of the system prompt, a NUL, then the user prompt: the bytes of the saved file."""
    return hashlib.sha256(_file_bytes(system, prompt)).hexdigest()


# --- the interface section ----------------------------------------------------------------------


def imported_modules(code: str) -> set[str]:
    """Top-level module names a piece of Python imports; empty when it does not parse."""
    return set(_imported_names(code))


def _imported_names(code: str) -> dict[str, set[str]]:
    """Module -> the names the code takes from it, by `from m import a` and by `m.a` after
    `import m`. A name used some other way (passed around as a module) is not found."""
    try:
        tree = ast.parse(code.removeprefix("﻿"))
    except (SyntaxError, ValueError):
        return {}
    found: dict[str, set[str]] = defaultdict(set)
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                found.setdefault(top, set())
                aliases[a.asname or top] = top
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top = node.module.split(".")[0]
            found[top] |= {a.name for a in node.names if a.name != "*"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            found[aliases[node.value.id]].add(node.attr)
    return dict(found)


def owns_module(task: Task, module: str) -> bool:
    """Whether the task owns the file or package that `import module` finds. A task that owns the
    whole workspace ('.') is not an interface to name: it owns every module."""
    wanted = (PurePosixPath(module), PurePosixPath(f"{module}.py"))
    return any(PurePosixPath(p) in wanted for p in task.paths)


def _own_check_code(sheet: TermSheet, task: Task, checks_dir: Path) -> list[str]:
    return [
        (checks_dir / c.file).read_text(encoding="utf-8") for c in sheet.checks if c.task == task.id
    ]


def derive_reads(sheet: TermSheet, checks_dir: Path) -> dict[str, tuple[str, ...]]:
    """For each task, the other tasks whose files its own checks import. Reads this task's check
    files only, and finds ids, not code."""
    reads: dict[str, tuple[str, ...]] = {}
    for task in sheet.tasks:
        modules: set[str] = set()
        for code in _own_check_code(sheet, task, checks_dir):
            modules |= imported_modules(code)
        reads[task.id] = tuple(
            other.id
            for other in sheet.tasks
            if other.id != task.id and any(owns_module(other, m) for m in modules)
        )
    return reads


def interfaces_section(sheet: TermSheet, task: Task, checks_dir: Path) -> str:
    """The names this task's checks take from files that tasks in `dispatch.reads` own. Names
    only: the other task's code is its own. An empty string when there is nothing to say."""
    if task.dispatch is None or not task.dispatch.reads:
        return ""
    taken: dict[str, set[str]] = defaultdict(set)
    for code in _own_check_code(sheet, task, checks_dir):
        for module, names in _imported_names(code).items():
            taken[module] |= names
    lines = []
    for other in sheet.tasks:
        if other.id not in task.dispatch.reads:
            continue
        for module in sorted(taken):
            if owns_module(other, module) and taken[module]:
                first = sorted(taken[module])[:_MAX_NAMES_PER_FILE]
                shown = ", ".join(safe_text(n, limit=60) for n in first)
                lines.append(f"- {safe_text(module, limit=60)} (built by task {other.id}): {shown}")
    if not lines:
        return ""
    return _PART_SEP.join(
        [
            "Other tasks build these names. Your checks use them; they are not yours to write:",
            "\n".join(lines),
        ]
    )


# --- the bundle ---------------------------------------------------------------------------------


def _parts(
    sheet: TermSheet, task: Task, checks_dir: Path, inputs: SliceInputs, levels: Levels
) -> list[tuple[str, str]]:
    if inputs.resume:
        text = briefs.continuation_prompt(
            inputs.gate_results,
            inputs.disputed,
            inputs.denied_tools,
            task.paths[0],
            inputs.notes,
            inputs.denial_reasons,
        )
        return [("gate", text)]
    first = briefs.task_prompt(sheet, task, checks_dir)
    parts = [("task", first)]
    if levels.interfaces:
        parts.append(("interfaces", interfaces_section(sheet, task, checks_dir)))
    h = inputs.handoff
    if h is not None:
        full = briefs.reassignment_brief(
            first,
            fired=h.fired,
            history=h.history,
            gate_results=h.gate_results,
            kept=h.kept,
            with_files=levels.files,
            with_tails=levels.tails,
        )
        # the brief is the task prompt followed by the handoff: name the two parts apart
        tail = full[len(first) :].lstrip("\n") if full.startswith(first) else ""
        parts.append(("handoff", tail) if tail else ("task", full))
    parts.append(("notes", _PART_SEP.join(inputs.notes)))
    return [(name, text) for name, text in parts if text]


def build_bundle(
    sheet: TermSheet,
    task: Task,
    checks_dir: Path,
    *,
    system: str,
    inputs: SliceInputs,
    bound: int = MAX_BUNDLE_CHARS,
) -> Bundle:
    """The slice's prompt, with the optional parts left out in `DROP_ORDER` until it is at most
    `bound` characters. BundleTooBig when the mandatory parts alone are over it."""
    for levels in DROP_ORDER:
        parts = _parts(sheet, task, checks_dir, inputs, levels)
        prompt = _PART_SEP.join(text for _, text in parts)
        if len(prompt) <= bound:
            dropped = tuple(
                name
                for name, kept in (
                    ("interfaces", levels.interfaces),
                    ("files", levels.files),
                    ("tails", levels.tails),
                )
                if not kept
            )
            return Bundle(system, prompt, {name: len(text) for name, text in parts}, dropped)
    raise BundleTooBig(task.id, {name: len(text) for name, text in parts}, bound)


def first_context_chars(sheet: TermSheet, task: Task, checks_dir: Path) -> int:
    """How long the first brief of a task is: what the term sheet's dispatch table shows. A check
    file that cannot be read counts as 0; the sheet's own validation reports it."""
    try:
        parts = _parts(sheet, task, checks_dir, SliceInputs(), DROP_ORDER[0])
    except (OSError, UnicodeDecodeError):
        return 0
    return len(_PART_SEP.join(text for _, text in parts))


# --- what the ledger and the folder can prove -----------------------------------------------------


def write_prompt(paths: RunPaths, worker: str, number: int, bundle: Bundle) -> None:
    target = paths.prompt(worker, number)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(bundle.file_bytes())


def verify(paths: RunPaths, events: Sequence[Event]) -> list[str]:
    """One line for each slice whose saved prompt is missing or no longer hashes to what its
    `slice_start` recorded. Only the latest start of a slice counts: a restarted slice rewrites
    its file. A run without dispatch records no hash and has nothing to check."""
    latest: dict[tuple[str, int], str] = {}
    for e in events:
        want, number = e.data.get("context_sha256"), e.data.get("slice")
        # Ledger data is not trusted to be well formed: a bad `slice` skips the line, never raises.
        if e.event is EventType.SLICE_START and isinstance(want, str) and type(number) is int:
            latest[(e.actor.removeprefix("worker:"), number)] = want
    problems = []
    for (worker, number), want in sorted(latest.items()):
        try:
            data = paths.prompt(worker, number).read_bytes()
        except OSError:
            problems.append(f"{worker} slice {number}: its prompt file is missing")
            continue
        if hashlib.sha256(data).hexdigest() != want:
            problems.append(f"{worker} slice {number}: its prompt file is not what was recorded")
    return problems
