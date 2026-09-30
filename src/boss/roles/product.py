"""The product department: turn the idea into user stories, and check the stories against it.

`product_manager` drafts the stories and its output is gated by `story_problems`. `user_agent`
reads them as the person who asked and says what is missing or misread; it is advisory, so its
output is shown to the investor and never edits the stories. Both are one call with no tools,
and neither records anything: the caller books the usage each function returns.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from boss.roles.base import RoleOutputError, RoleSpec, call_role
from boss.roles.stories import (
    MIN_SOURCE_CHARS,
    STORIES_SCHEMA,
    Stories,
    StoriesError,
    is_fragment,
    normalise,
    parse_stories,
    story_problems,
)
from boss.stream import Usage
from boss.worker import CLI

PRODUCT_MANAGER = RoleSpec(
    name="product_manager",
    department="product",
    reports_to="boss",
    purpose="turns the idea into user stories with acceptance criteria, each quoting the idea",
    gate="story_problems: shape, ids, at least one must story, every criterion source is a "
    "word-for-word fragment of the idea",
    prompt="product_manager_v1.md",
    skills=(
        "product_manager/reading-the-idea",
        "product_manager/story-splitting",
        "product_manager/acceptance-criteria",
    ),
)

USER_AGENT = RoleSpec(
    name="user_agent",
    department="product",
    reports_to="product_manager",
    purpose="advisory: reads the stories as the requester and says what the idea asks for that "
    "no criterion tests (missing) and what a criterion says that the idea does not (misread)",
    gate="review_problems: every quote is a word-for-word fragment of the idea, every criterion "
    "id exists, verdict is revise exactly when there is a finding; advisory, the stories are "
    "never changed by it",
    prompt="user_agent_v1.md",
    skills=("user_agent/reading-as-the-requester", "user_agent/quoting-the-idea"),
)

SPECS = (PRODUCT_MANAGER, USER_AGENT)


def write_stories(
    idea: str,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
) -> tuple[Stories, Usage]:
    """One call; the stories pass `story_problems` or this raises `RoleOutputError` listing every
    problem, carrying the usage of the call that was paid for. `RoleError` if the call failed.

    There is deliberately no repair call (a second call shown the problems). It would double the
    cost on exactly the runs where the model is already confused, the house shape is one model
    call, and nothing measures that a repaired draft is better than a fresh one. The seam is
    ready: `RoleOutputError.problems` is what a repair prompt would show.
    kn: add a bounded repair when a measured gate-failure rate on real ideas is high and a
    repair fixes most of them, booking each call's usage separately.
    """
    if not idea.strip():
        raise ValueError("idea must be non-empty text")
    out = call_role(
        PRODUCT_MANAGER,
        f"Idea:\n{idea.strip()}",
        STORIES_SCHEMA,
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
    )
    try:
        stories = parse_stories(out.data)
    except StoriesError as exc:
        raise RoleOutputError(PRODUCT_MANAGER.name, [str(exc)], out.usage) from exc
    if problems := story_problems(stories, idea):
        raise RoleOutputError(PRODUCT_MANAGER.name, problems, out.usage)
    return stories, out.usage


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_LIST_MARKER = re.compile(r"(?:\d+|[A-Za-z])[.)]")
_ITEM = re.compile(r"(?:(?:\d+|[A-Za-z])[.)]|[-*+•])\s")


def uncovered_fragments(idea: str, stories: Stories) -> list[str]:
    """The sentences of the idea that no criterion's `source` overlaps, in order. No model.

    A fragment is a sentence: consecutive prose lines are read as one paragraph (a hard-wrapped
    sentence is one fragment) that ends at a blank line, a code line, or a line starting a list
    item (`3.`, `b)`, `-`, `*`, `+`), and the paragraph is cut after `.`, `!` or `?` followed by
    white space. A list marker stays with its item. Lines indented four spaces or a tab, and
    lines between ``` fences, are code: each is a fragment and is never cut. Fence lines, and
    fragments with no letter in them (`---`, a bare number), are not reported.
    kn: two requirements on unterminated consecutive lines read as one fragment.

    A source overlaps a fragment when the normalised source (`normalise`: lower case, single
    spaces) occurs in the normalised idea at a place that shares at least one character with the
    fragment. So a quote spanning two sentences covers both, a source that occurs twice covers
    every occurrence, and a source shorter than MIN_SOURCE_CHARS or not in the idea covers
    nothing. Whether a source is grounded is `story_problems`' job, not this function's.
    """
    fragments = _fragments(idea)
    normalised = [normalise(f) for f in fragments]
    haystack = " ".join(normalised)
    starts, position = [], 0
    for text in normalised:
        starts.append(position)
        position += len(text) + 1
    covered: set[int] = set()
    for criterion in stories.criteria():
        source = normalise(criterion.source)
        if len(source) < MIN_SOURCE_CHARS:
            continue
        at = haystack.find(source)
        while at != -1:
            end = at + len(source)
            covered.update(
                n
                for n, (start, text) in enumerate(zip(starts, normalised, strict=True))
                if start < end and at < start + len(text)
            )
            at = haystack.find(source, at + 1)
    return [
        fragment
        for n, fragment in enumerate(fragments)
        if n not in covered
        and any(ch.isalpha() for ch in fragment)
        and not fragment.startswith("```")
    ]


def _fragments(idea: str) -> list[str]:
    found: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            found.extend(_sentences(" ".join(paragraph)))
            paragraph.clear()

    in_fence = False
    for line in idea.splitlines():
        text = line.strip()
        if text.startswith("```"):
            flush()
            in_fence = not in_fence
            found.append(text)
        elif in_fence or line.startswith(("    ", "\t")) or not text:
            flush()
            if text:
                found.append(text)
        else:
            if _ITEM.match(text):
                flush()
            paragraph.append(text)
    flush()
    return found


def _sentences(line: str) -> list[str]:
    out: list[str] = []
    marker = ""
    for piece in _SENTENCE_END.split(line):
        if _LIST_MARKER.fullmatch(piece):
            marker = f"{marker}{piece} "
            continue
        out.append(marker + piece)
        marker = ""
    if marker:
        out.append(marker.strip())
    return out


MAX_FINDINGS = 8  # across missing and misread: the investor reads all of them
VERDICTS = ("accept", "revise")
_TEXT = {"type": "string", "minLength": 1}


def _findings(**fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "array",
        "maxItems": MAX_FINDINGS,
        "items": {"type": "object", "properties": fields, "required": list(fields)},
    }


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "missing": _findings(quote=_TEXT, why=_TEXT),
        "misread": _findings(criterion={"type": "string"}, quote=_TEXT, why=_TEXT),
        "verdict": {"type": "string", "enum": list(VERDICTS)},
    },
    "required": ["missing", "misread", "verdict"],
}


@dataclass(frozen=True, slots=True)
class Missing:
    quote: str  # a fragment of the idea that no criterion tests
    why: str


@dataclass(frozen=True, slots=True)
class Misread:
    criterion: str  # id of a criterion, e.g. "S1.2"
    quote: str  # the fragment of the idea it conflicts with
    why: str


@dataclass(frozen=True, slots=True)
class StoryReview:
    """Advice for the investor. Nothing in the firm acts on it by itself."""

    missing: tuple[Missing, ...]
    misread: tuple[Misread, ...]
    verdict: str  # one of VERDICTS

    def to_data(self) -> dict[str, Any]:
        return {
            "missing": [{"quote": m.quote, "why": m.why} for m in self.missing],
            "misread": [
                {"criterion": m.criterion, "quote": m.quote, "why": m.why} for m in self.misread
            ],
            "verdict": self.verdict,
        }


class ReviewError(ValueError):
    """The data is not shaped like a story review at all (as opposed to one with problems)."""


def parse_review(data: object) -> StoryReview:
    """Build a StoryReview from schema-shaped data. Raises ReviewError on a wrong shape; whether
    its findings hold is `review_problems`' job."""
    try:
        if not isinstance(data, Mapping):
            raise TypeError("not an object")
        return StoryReview(
            tuple(Missing(_str(m, "quote"), _str(m, "why")) for m in _list(data, "missing")),
            tuple(
                Misread(_str(m, "criterion"), _str(m, "quote"), _str(m, "why"))
                for m in _list(data, "misread")
            ),
            _str(data, "verdict"),
        )
    except (KeyError, TypeError) as exc:
        raise ReviewError(f"not shaped like a story review: {exc}") from exc


def review_problems(review: StoryReview, idea: str, stories: Stories) -> list[str]:
    """Everything wrong with a review, as one line each. Empty means it passes the gate."""
    problems: list[str] = []
    count = len(review.missing) + len(review.misread)
    if count > MAX_FINDINGS:
        problems.append(f"at most {MAX_FINDINGS} findings in all, has {count}")
    for n, missing in enumerate(review.missing, start=1):
        problems += _finding_problems(f"missing {n}", missing.quote, missing.why, idea)
    known = {c.id for c in stories.criteria()}
    for n, misread in enumerate(review.misread, start=1):
        label = f"misread {n}"
        if misread.criterion not in known:
            problems.append(f"{label}: there is no criterion {misread.criterion!r}")
        problems += _finding_problems(label, misread.quote, misread.why, idea)
    if review.verdict not in VERDICTS:
        problems.append(f"verdict must be one of {', '.join(VERDICTS)}, is {review.verdict!r}")
    elif (review.verdict == "revise") != (count > 0):
        problems.append(
            f"verdict is {review.verdict!r} with {count} findings; it must be 'revise' exactly "
            "when there is at least one"
        )
    return problems


def review_stories(
    idea: str,
    stories: Stories,
    *,
    env: Mapping[str, str],
    model: str,
    executable: str = CLI,
    thinking_tokens: int | None = None,
) -> tuple[StoryReview, Usage]:
    """One call: the idea and the stories go to the user agent, which says what is missing or
    misread. ADVISORY: the review is shown to the investor and never changes the stories, and a
    `revise` verdict is a suggestion, not a gate. What is gated is the review itself: it must
    pass `review_problems` or this raises `RoleOutputError` listing every problem, with the
    usage of the call that was paid for. `RoleError` if the call failed.
    """
    if not idea.strip():
        raise ValueError("idea must be non-empty text")
    listing = json.dumps(stories.to_data(), indent=2)
    out = call_role(
        USER_AGENT,
        f"Idea:\n{idea.strip()}\n\nStories:\n{listing}",
        REVIEW_SCHEMA,
        env=env,
        model=model,
        executable=executable,
        thinking_tokens=thinking_tokens,
    )
    try:
        review = parse_review(out.data)
    except ReviewError as exc:
        raise RoleOutputError(USER_AGENT.name, [str(exc)], out.usage) from exc
    if problems := review_problems(review, idea, stories):
        raise RoleOutputError(USER_AGENT.name, problems, out.usage)
    return review, out.usage


def _finding_problems(label: str, quote: str, why: str, idea: str) -> list[str]:
    problems = []
    if len(normalise(quote)) < MIN_SOURCE_CHARS:
        problems.append(f"{label}: quote must be at least {MIN_SOURCE_CHARS} characters")
    elif not is_fragment(quote, idea):
        problems.append(f"{label}: quote is not a fragment of the idea: {quote!r}")
    if not why.strip():
        problems.append(f"{label}: why is empty")
    return problems


def _str(item: object, key: str) -> str:
    value = item[key]  # type: ignore[index]
    if not isinstance(value, str):
        raise TypeError(f"{key} is not text")
    return value


def _list(item: object, key: str) -> list[Any]:
    value = item[key]  # type: ignore[index]
    if not isinstance(value, list):
        raise TypeError(f"{key} is not a list")
    return value
