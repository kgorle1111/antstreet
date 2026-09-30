"""Engineering roles: split the stories into tasks (the system designer), then write checks that
must cover every acceptance criterion (the tester), and assemble a term sheet from both.

Each role is one structured call with no tools. The model drafts; code decides: ids and file names
are computed here, every rule `termsheet` already has for tasks and check files is reused, and
nothing is recorded (the caller books each call's usage under its own role).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from boss.roles.base import RoleOutputError, RoleSpec, call_role
from boss.roles.stories import Stories
from boss.stream import Usage
from boss.termsheet import (
    CheckSpec,
    Task,
    TermSheet,
    _id_problems,
    _ownership_problems,
)
from boss.worker import CLI

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
SPECS = (SYSTEM_DESIGNER,)


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
