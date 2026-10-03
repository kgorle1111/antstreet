# extract_headings does not skip fenced code blocks, so '# comment' lines in code become headings.
import re
from dataclasses import dataclass

_ATX = re.compile(r" {0,3}(#{1,6})(?:[ \t]+(.*))?")
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+[ \t]*$")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int
    anchor: str


def slugify(text):
    kept = "".join(c for c in text.lower() if c.isalnum() or c in "_- ")
    return kept.replace(" ", "-") or "section"


def _check(markdown):
    if not isinstance(markdown, str):
        raise ValueError("markdown must be a str")


def fenced_lines(markdown):
    _check(markdown)
    inside, fence = set(), None
    for number, line in enumerate(markdown.split("\n"), 1):
        found = _FENCE.fullmatch(line)
        if fence is None:
            if found:
                fence = found.group(1)
                inside.add(number)
            continue
        inside.add(number)
        if (
            found
            and found.group(1)[0] == fence[0]
            and len(found.group(1)) >= len(fence)
            and not found.group(2).strip(" \t")
        ):
            fence = None
    return inside


def extract_headings(markdown):
    _check(markdown)
    skip = set()
    found, taken = [], set()
    for number, line in enumerate(markdown.split("\n"), 1):
        match = None if number in skip else _ATX.fullmatch(line)
        if not match:
            continue
        text = _CLOSING.sub("", (match.group(2) or "").strip()).strip()
        if not text:
            continue
        slug = slugify(text)
        anchor, suffix = slug, 0
        while anchor in taken:
            suffix += 1
            anchor = f"{slug}-{suffix}"
        taken.add(anchor)
        found.append(Heading(len(match.group(1)), text, number, anchor))
    return found
