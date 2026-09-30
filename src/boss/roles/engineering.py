"""Engineering roles: split the stories into tasks (the system designer), then write checks that
must cover every acceptance criterion (the tester), and assemble a term sheet from both.

Each role is one structured call with no tools. The model drafts; code decides: ids and file names
are computed here, every rule `termsheet` already has for tasks and check files is reused, and
nothing is recorded (the caller books each call's usage under its own role).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boss.errors import Outcome
from boss.redact import safe_text
from boss.roles.base import RoleError, RoleOutputError, RoleSpec, call_role
from boss.roles.stories import Stories
from boss.stream import Usage
from boss.termsheet import (
    CheckSpec,
    Task,
    TermSheet,
    _id_problems,
    _ownership_problems,
    check_file_problems,
)
from boss.worker import CLI

MAX_CHECKS = 16  # each is a pytest run in the gate, and the stories allow at most 16 criteria
MAX_LINE = 99  # the coverage matrix is read in a terminal, under 100 columns
_TAIL = 40  # columns for the checks (or the reason) at the end of a matrix line

SYSTEM_DESIGNER = RoleSpec(
    name="system_designer",
    department="engineering",
    reports_to="boss",
    purpose="splits the stories into tasks, each with the files it owns and its public interface",
    gate=(
        "task rules of the term sheet, at most max_tasks tasks, "
        "every story assigned to exactly one task, no task without a story"
    ),
    prompt="system_designer_v1.md",
    skills=(
        "system_designer/one-task-by-default",
        "system_designer/file-ownership",
        "system_designer/interfaces-from-the-idea",
    ),
)
TESTER = RoleSpec(
    name="tester",
    department="engineering",
    reports_to="system_designer",
    purpose="writes pytest checks that between them cover every acceptance criterion",
    gate=(
        "every cited criterion exists and belongs to the check's task; every criterion has a "
        f"check or an untestable reason, never both; at most {MAX_CHECKS} checks; every file "
        "is a valid pytest file"
    ),
    prompt="tester_v1.md",
    skills=(
        "tester/only-what-the-idea-states",
        "tester/one-behaviour-per-check",
        "tester/boundary-values",
    ),
    cap_micros=250_000,  # up to 16 complete test files in one answer
)
SPECS = (SYSTEM_DESIGNER, TESTER)

TESTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_CHECKS,
            "items": {
                "type": "object",
                "properties": {
                    "criteria": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                    "task": {"type": "string"},
                    "description": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["criteria", "task", "description", "code"],
            },
        },
        "untestable": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"criterion": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["criterion", "reason"],
            },
        },
    },
    "required": ["checks", "untestable"],
}


def design_schema(max_tasks: int) -> dict[str, Any]:
    texts = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "minItems": 1,
                "maxItems": max_tasks,
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "brief": {"type": "string"},
                        "paths": texts | {"minItems": 1},
                        "stories": texts | {"minItems": 1},
                        "interfaces": texts,
                    },
                    "required": ["id", "brief", "paths", "stories", "interfaces"],
                },
            }
        },
        "required": ["tasks"],
    }


@dataclass(frozen=True, slots=True)
class DesignTask:
    id: str
    brief: str
    paths: tuple[str, ...]  # files it owns
    stories: tuple[str, ...]  # story ids it delivers
    interfaces: tuple[str, ...]  # public names it must provide, one signature each

    def as_task(self) -> Task:
        """The term-sheet task. A builder sees only the brief, so the interfaces go in it."""
        brief = self.brief.strip()
        if self.interfaces:
            names = "\n".join(f"- {i}" for i in self.interfaces)
            brief += f"\n\nPublic interface, exactly:\n{names}"
        return Task(self.id, brief, self.paths)


@dataclass(frozen=True, slots=True)
class Design:
    tasks: tuple[DesignTask, ...]

    def owner_of(self, story_id: str) -> str | None:
        """The id of the task that delivers the story, if any."""
        return next((t.id for t in self.tasks if story_id in t.stories), None)


def design_tasks(
    idea: str,
    stories: Stories,
    *,
    max_tasks: int,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> tuple[Design, Usage]:
    """One call: split the stories into at most `max_tasks` tasks.

    Raises RoleError if the call fails and RoleOutputError, listing every problem, if the design
    breaks a rule in `design_problems`. Both carry the call's usage.
    """
    if max_tasks < 1:
        raise ValueError("max_tasks must be at least 1")
    prompt = f"Idea:\n{idea.strip()}\n\nStories:\n{stories_text(stories)}\n\n"
    prompt += f"Use at most {max_tasks} tasks."
    output = call_role(
        SYSTEM_DESIGNER,
        prompt,
        design_schema(max_tasks),
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
        timeout_s=timeout_s,
    )
    design, problems = _parse_design(output.data)
    if design is not None:
        problems = design_problems(design, stories, max_tasks=max_tasks)
    if design is None or problems:
        raise RoleOutputError(SYSTEM_DESIGNER.name, problems, output.usage)
    return design, output.usage


def design_problems(design: Design, stories: Stories, *, max_tasks: int) -> list[str]:
    """Everything wrong with a design, one line each. Empty means it passes the gate."""
    problems: list[str] = []
    if not 1 <= len(design.tasks) <= max_tasks:
        problems.append(f"needs 1 to {max_tasks} tasks, has {len(design.tasks)}")
    problems += _id_problems("task", [t.id for t in design.tasks])
    problems += [f"task {t.id} has an empty brief" for t in design.tasks if not t.brief.strip()]
    # The term sheet's own ownership rules, run on a sheet whose tasks each own one placeholder
    # check, so only the path rules can fire.
    sheet = TermSheet(
        "-",
        1,
        (),
        tuple(CheckSpec(f"c{n}", "-", "test_x.py", t.id) for n, t in enumerate(design.tasks)),
        tuple(Task(t.id, t.brief, t.paths) for t in design.tasks),
    )
    problems += _ownership_problems(sheet)
    known = {story.id for story in stories.stories}
    owners: dict[str, list[str]] = {}
    for task in design.tasks:
        if not task.stories:
            problems.append(f"task {task.id} delivers no story")
        for story_id in task.stories:
            if story_id in known:
                owners.setdefault(story_id, []).append(task.id)
            else:
                problems.append(f"task {task.id} names unknown story {story_id!r}")
    for story in stories.stories:
        found = owners.get(story.id, [])
        if len(found) != 1:
            where = ", ".join(found) if found else "no task"
            problems.append(f"story {story.id} must belong to exactly one task, is in: {where}")
    return problems


def stories_text(stories: Stories) -> str:
    """The stories as the roles read them: compact, with each criterion's quote from the idea."""
    lines: list[str] = []
    for story in stories.stories:
        lines.append(
            f"{story.id} [{story.priority}] As a {story.as_a}, I want {story.i_want}, "
            f"so that {story.so_that}."
        )
        for c in story.criteria:
            lines.append(f"  {c.id} given {c.given}; when {c.when}; then {c.then}")
            lines.append(f'      idea says: "{c.source}"')
    if stories.out_of_scope:
        lines.append("Out of scope: " + "; ".join(stories.out_of_scope))
    return "\n".join(lines)


def _parse_design(data: Mapping[str, Any]) -> tuple[Design | None, list[str]]:
    """The design, or every way the output is not shaped like one (then the design is None)."""
    problems: list[str] = []
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list):
        return None, ["tasks must be a list"]
    tasks = []
    for n, raw in enumerate(raw_tasks, start=1):
        where = f"task {n}"
        tasks.append(
            DesignTask(
                _text_in(raw, "id", where, problems),
                _text_in(raw, "brief", where, problems),
                _texts_in(raw, "paths", where, problems),
                _texts_in(raw, "stories", where, problems),
                _texts_in(raw, "interfaces", where, problems),
            )
        )
    return (None, problems) if problems else (Design(tuple(tasks)), [])


def _text_in(item: object, key: str, where: str, problems: list[str]) -> str:
    value = item.get(key) if isinstance(item, dict) else None
    if not isinstance(value, str):
        problems.append(f"{where}: {key} must be text")
        return ""
    return value


def _texts_in(item: object, key: str, where: str, problems: list[str]) -> tuple[str, ...]:
    value = item.get(key) if isinstance(item, dict) else None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        problems.append(f"{where}: {key} must be a list of text")
        return ()
    return tuple(value)


@dataclass(frozen=True, slots=True)
class Untestable:
    criterion: str
    reason: str  # one line, from the tester


@dataclass(frozen=True, slots=True)
class TestPlan:
    __test__ = False  # not a pytest class, whatever its name says

    checks: tuple[CheckSpec, ...]  # ids, files and criteria are ours; the code is in the files
    untestable: tuple[Untestable, ...]


@dataclass(frozen=True, slots=True)
class _RawCheck:
    criteria: tuple[str, ...]
    task: str
    description: str
    code: str


def write_checks(
    idea: str,
    stories: Stories,
    design: Design,
    checks_dir: Path,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
    timeout_s: float = 300.0,
) -> tuple[TestPlan, Usage]:
    """One call: write pytest checks for the criteria, and write them into `checks_dir` as
    `test_c01.py`, `test_c02.py`, ... (ids and names are ours, not the model's).

    Raises RoleError if the call fails or the files cannot be written, and RoleOutputError,
    listing every problem, if the output breaks a rule in the tester's gate. Both carry the call's
    usage, and a rejected output leaves no check file behind.
    """
    prompt = (
        f"Idea:\n{idea.strip()}\n\nStories and acceptance criteria:\n{stories_text(stories)}"
        f"\n\nDesign:\n{design_text(design)}\n\nWrite at most {MAX_CHECKS} checks."
    )
    output = call_role(
        TESTER,
        prompt,
        TESTS_SCHEMA,
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
        timeout_s=timeout_s,
    )
    raw, untestable, problems = _parse_tests(output.data)
    if not problems:
        problems = _plan_problems(stories, design, raw, untestable)
    if problems:
        raise RoleOutputError(TESTER.name, problems, output.usage)
    specs = tuple(
        CheckSpec(f"c{n:02d}", r.description.strip(), f"test_c{n:02d}.py", r.task, r.criteria)
        for n, r in enumerate(raw, start=1)
    )
    written: list[Path] = []
    try:
        checks_dir.mkdir(parents=True, exist_ok=True)
        for spec, r in zip(specs, raw, strict=True):
            written.append(checks_dir / spec.file)
            written[-1].write_text(r.code, encoding="utf-8")
    except OSError as exc:
        _remove(written)
        message = f"cannot write the check files: {exc}"
        raise RoleError(TESTER.name, message, Outcome.COMPLETED, output.usage) from exc
    problems = [p for spec in specs for p in check_file_problems(spec, checks_dir)]
    if problems:
        _remove(written)
        raise RoleOutputError(TESTER.name, problems, output.usage)
    return TestPlan(specs, tuple(untestable)), output.usage


def coverage(stories: Stories, checks: Sequence[CheckSpec]) -> dict[str, tuple[str, ...]]:
    """Each criterion id, in story order, with the ids of the checks citing it, in check order."""
    return _cover([c.id for c in stories.criteria()], ((k.id, k.criteria) for k in checks))


def render_coverage(
    stories: Stories, checks: Sequence[CheckSpec], untestable: Sequence[Untestable]
) -> str:
    """The matrix the investor reads before approving: one line per criterion, with its `then`
    and the checks that cover it, or UNTESTABLE and why. Under 100 columns; every piece of model
    text is made safe and put on one line."""
    covered = coverage(stories, checks)
    reasons = {u.criterion: u.reason for u in untestable}
    ids = {cid: _flat(cid, 8) for cid in covered}
    pad = max((len(i) for i in ids.values()), default=0) + 1
    room = MAX_LINE - pad - 2 - _TAIL
    lines = []
    for criterion in stories.criteria():
        cid = criterion.id
        if covered[cid]:
            tail = ", ".join(covered[cid])
        elif cid in reasons:
            tail = f"UNTESTABLE: {reasons[cid]}"
        else:
            tail = "NO CHECK"
        then = _flat(criterion.then, room).ljust(room)
        lines.append(f"{ids[cid].ljust(pad)}{then}  {_flat(tail, _TAIL)}".rstrip())
    n_covered = sum(1 for found in covered.values() if found)
    n_untestable = sum(1 for cid, found in covered.items() if not found and cid in reasons)
    lines.append(
        f"{len(covered)} criteria: {n_covered} covered, {n_untestable} untestable, "
        f"{len(covered) - n_covered - n_untestable} with no check"
    )
    return "\n".join(lines)


def design_text(design: Design) -> str:
    lines: list[str] = []
    for task in design.tasks:
        lines.append(f"{task.id}: {task.brief.strip()}")
        lines.append(f"  owns: {', '.join(task.paths)}")
        lines.append(f"  delivers: {', '.join(task.stories)}")
        lines += [f"  interface: {name}" for name in task.interfaces]
    return "\n".join(lines)


def _cover(
    criterion_ids: Iterable[str], cites: Iterable[tuple[str, tuple[str, ...]]]
) -> dict[str, tuple[str, ...]]:
    found: dict[str, list[str]] = {cid: [] for cid in criterion_ids}
    for check_id, cited in cites:
        for cid in dict.fromkeys(cited):
            if cid in found:
                found[cid].append(check_id)
    return {cid: tuple(ids) for cid, ids in found.items()}


def _plan_problems(
    stories: Stories, design: Design, raw: Sequence[_RawCheck], untestable: Sequence[Untestable]
) -> list[str]:
    problems: list[str] = []
    story_of = {c.id: story.id for story in stories.stories for c in story.criteria}
    tasks = {t.id for t in design.tasks}
    if not 1 <= len(raw) <= MAX_CHECKS:
        problems.append(f"needs 1 to {MAX_CHECKS} checks, has {len(raw)}")
    for n, check in enumerate(raw, start=1):
        name = f"check c{n:02d}"
        if not check.description.strip():
            problems.append(f"{name} has no description")
        if not check.criteria:
            problems.append(f"{name} cites no criterion")
        if len(set(check.criteria)) != len(check.criteria):
            problems.append(f"{name} cites a criterion twice")
        if check.task not in tasks:
            problems.append(f"{name} belongs to unknown task {check.task!r}")
        for cid in dict.fromkeys(check.criteria):
            if cid not in story_of:
                problems.append(f"{name} cites unknown criterion {cid!r}")
            elif check.task in tasks and design.owner_of(story_of[cid]) != check.task:
                owner = design.owner_of(story_of[cid])
                problems.append(f"{name} belongs to {check.task} but {cid} is delivered by {owner}")
    covered = _cover(story_of, ((f"c{n:02d}", c.criteria) for n, c in enumerate(raw, start=1)))
    listed: set[str] = set()
    for item in untestable:
        if item.criterion not in story_of:
            problems.append(f"untestable names unknown criterion {item.criterion!r}")
        elif item.criterion in listed:
            problems.append(f"{item.criterion} is listed untestable twice")
        elif covered[item.criterion]:
            by = ", ".join(covered[item.criterion])
            problems.append(f"{item.criterion} is covered by {by} and also listed untestable")
        if not item.reason.strip():
            problems.append(f"untestable {item.criterion} has no reason")
        listed.add(item.criterion)
    problems += [
        f"criterion {cid} has no check and is not listed untestable"
        for cid, ids in covered.items()
        if not ids and cid not in listed
    ]
    problems += [
        f"task {t.id} has no check, so its progress cannot be measured"
        for t in design.tasks
        if not any(check.task == t.id for check in raw)
    ]
    return problems


def _parse_tests(data: Mapping[str, Any]) -> tuple[list[_RawCheck], list[Untestable], list[str]]:
    """The checks and untestable criteria as data, plus every way the output is not shaped like
    them. With any such problem the data is incomplete and must not be gated."""
    problems: list[str] = []
    raw_checks, raw_untestable = data.get("checks"), data.get("untestable", [])
    if not isinstance(raw_checks, list):
        problems.append("checks must be a list")
        raw_checks = []
    if not isinstance(raw_untestable, list):
        problems.append("untestable must be a list")
        raw_untestable = []
    checks = []
    for n, item in enumerate(raw_checks, start=1):
        where = f"check {n}"
        code = _text_in(item, "code", where, problems)
        try:
            code.encode("utf-8")
        except UnicodeEncodeError:
            problems.append(f"{where}: code is not valid text")
        checks.append(
            _RawCheck(
                _texts_in(item, "criteria", where, problems),
                _text_in(item, "task", where, problems),
                _text_in(item, "description", where, problems),
                code,
            )
        )
    untestable = [
        Untestable(
            _text_in(item, "criterion", f"untestable {n}", problems),
            _text_in(item, "reason", f"untestable {n}", problems),
        )
        for n, item in enumerate(raw_untestable, start=1)
    ]
    return checks, untestable, problems


def _flat(text: str, limit: int) -> str:
    """Model text made safe to show, on one line, at most `limit` characters."""
    return safe_text(" ".join(safe_text(text, limit=limit * 4).split()), limit=limit)


def _remove(paths: Sequence[Path]) -> None:
    for path in paths:
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
