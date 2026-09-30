"""The product department: turn the idea into user stories, and check the stories against it.

`product_manager` drafts the stories and its output is gated by `story_problems`. `user_agent`
reads them as the person who asked and says what is missing or misread; it is advisory, so its
output is shown to the investor and never edits the stories. Both are one call with no tools,
and neither records anything: the caller books the usage each function returns.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from boss.roles.base import RoleOutputError, RoleSpec, call_role
from boss.roles.stories import (
    MIN_SOURCE_CHARS,
    STORIES_SCHEMA,
    Stories,
    StoriesError,
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

SPECS = (PRODUCT_MANAGER,)


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
