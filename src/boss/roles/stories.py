"""User stories and acceptance criteria: the shared contract between the product manager, who
writes them, the tester, who must cover every criterion with a check, and the investor, who
reads them before funding anything.

Every criterion names the fragment of the investor's idea it comes from, word for word. That is
checked by code: a requirement the idea does not contain cannot enter the plan unnoticed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_STORIES = 8
MAX_CRITERIA = 16  # across all stories: each needs at least one check, and checks cost gate time
MIN_SOURCE_CHARS = 8  # shorter fragments match by accident
PRIORITIES = ("must", "should", "could")
_STORY_ID = re.compile(r"S[1-9]\d?")
_TEXT = {"type": "string", "minLength": 1}

STORIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_STORIES,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "as_a": _TEXT,
                    "i_want": _TEXT,
                    "so_that": _TEXT,
                    "priority": {"type": "string", "enum": list(PRIORITIES)},
                    "criteria": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "given": _TEXT,
                                "when": _TEXT,
                                "then": _TEXT,
                                "source": _TEXT,
                            },
                            "required": ["id", "given", "when", "then", "source"],
                        },
                    },
                },
                "required": ["id", "as_a", "i_want", "so_that", "priority", "criteria"],
            },
        },
        "out_of_scope": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["stories"],
}


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str  # "<story id>.<n>", e.g. "S2.1"
    given: str
    when: str
    then: str
    source: str  # the fragment of the idea this criterion comes from, word for word


@dataclass(frozen=True, slots=True)
class Story:
    id: str  # "S1", "S2", ...
    as_a: str
    i_want: str
    so_that: str
    priority: str  # one of PRIORITIES
    criteria: tuple[Criterion, ...]


@dataclass(frozen=True, slots=True)
class Stories:
    stories: tuple[Story, ...]
    out_of_scope: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()

    def criteria(self) -> tuple[Criterion, ...]:
        return tuple(c for story in self.stories for c in story.criteria)

    def to_data(self) -> dict[str, Any]:
        return {
            "stories": [
                {
                    "id": s.id,
                    "as_a": s.as_a,
                    "i_want": s.i_want,
                    "so_that": s.so_that,
                    "priority": s.priority,
                    "criteria": [
                        {
                            "id": c.id,
                            "given": c.given,
                            "when": c.when,
                            "then": c.then,
                            "source": c.source,
                        }
                        for c in s.criteria
                    ],
                }
                for s in self.stories
            ],
            "out_of_scope": list(self.out_of_scope),
            "open_questions": list(self.open_questions),
        }


class StoriesError(ValueError):
    """The data is not shaped like stories at all (as opposed to stories with problems)."""


def parse_stories(data: object) -> Stories:
    """Build Stories from schema-shaped data. Raises StoriesError on a wrong shape; whether the
    stories are any good is `story_problems`' job."""
    try:
        if not isinstance(data, Mapping):
            raise TypeError("not an object")
        stories = tuple(
            Story(
                id=_text(s, "id"),
                as_a=_text(s, "as_a"),
                i_want=_text(s, "i_want"),
                so_that=_text(s, "so_that"),
                priority=_text(s, "priority"),
                criteria=tuple(
                    Criterion(*(_text(c, key) for key in ("id", "given", "when", "then", "source")))
                    for c in _list(s, "criteria")
                ),
            )
            for s in _list(data, "stories")
        )
        return Stories(
            stories,
            tuple(_texts(data, "out_of_scope")),
            tuple(_texts(data, "open_questions")),
        )
    except (KeyError, TypeError) as exc:
        raise StoriesError(f"not shaped like stories: {exc}") from exc


def story_problems(stories: Stories, idea: str) -> list[str]:
    """Everything wrong with a set of stories, as one line each. Empty means it passes the gate."""
    problems: list[str] = []
    if not 1 <= len(stories.stories) <= MAX_STORIES:
        problems.append(f"needs 1 to {MAX_STORIES} stories, has {len(stories.stories)}")
    if len(stories.criteria()) > MAX_CRITERIA:
        problems.append(f"at most {MAX_CRITERIA} criteria in all, has {len(stories.criteria())}")
    haystack = normalise(idea)
    for n, story in enumerate(stories.stories, start=1):
        if story.id != f"S{n}" or not _STORY_ID.fullmatch(story.id):
            problems.append(f"story {n} must have id S{n}, has {story.id!r}")
        if story.priority not in PRIORITIES:
            problems.append(f"{story.id}: priority must be one of {', '.join(PRIORITIES)}")
        for field in ("as_a", "i_want", "so_that"):
            if not getattr(story, field).strip():
                problems.append(f"{story.id}: {field} is empty")
        if not story.criteria:
            problems.append(f"{story.id}: needs at least one acceptance criterion")
        for m, criterion in enumerate(story.criteria, start=1):
            expected = f"S{n}.{m}"
            if criterion.id != expected:
                problems.append(f"{story.id}: criterion {m} must have id {expected}")
            for field in ("given", "when", "then"):
                if not getattr(criterion, field).strip():
                    problems.append(f"{expected}: {field} is empty")
            source = normalise(criterion.source)
            if len(source) < MIN_SOURCE_CHARS:
                problems.append(
                    f"{expected}: source must quote at least {MIN_SOURCE_CHARS} characters"
                )
            elif source not in haystack:
                problems.append(
                    f"{expected}: source is not a fragment of the idea: {criterion.source!r}"
                )
    if not any(story.priority == "must" for story in stories.stories):
        problems.append("at least one story must have priority 'must'")
    return problems


def normalise(text: str) -> str:
    """Lower case, single spaces: a quote may differ from the idea in case and line breaks only."""
    return " ".join(text.lower().split())


def is_fragment(quote: str, idea: str) -> bool:
    """True when `quote`, once normalised, is a non-empty piece of the normalised idea. Length
    limits are the caller's: a two-letter quote is a fragment of almost anything."""
    needle = normalise(quote)
    return bool(needle) and needle in normalise(idea)


def _text(item: object, key: str) -> str:
    value = item[key]  # type: ignore[index]
    if not isinstance(value, str):
        raise TypeError(f"{key} is not text")
    return value


def _list(item: object, key: str) -> list[Any]:
    value = item[key]  # type: ignore[index]
    if not isinstance(value, list):
        raise TypeError(f"{key} is not a list")
    return value


def _texts(item: Mapping[str, Any], key: str) -> list[str]:
    value = item.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise TypeError(f"{key} is not a list of text")
    return value
