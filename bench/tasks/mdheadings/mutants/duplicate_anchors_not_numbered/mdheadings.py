# Headings with the same title all get the same anchor, with no -1, -2 counter.
import re

_ATX = re.compile(r"(#{1,6})(?:[ \t]+(.*))?")
_FENCE = re.compile(r"`{3,}|~{3,}")
_CLOSING = re.compile(r"(?:^|[ \t]+)#+$")


def _slug(title: str) -> str:
    kept = "".join(c for c in title.lower() if c.isalnum() or c in " -_")
    return kept.replace(" ", "-") or "section"


def extract_headings(markdown: str) -> list[tuple[int, str, str]]:
    if not isinstance(markdown, str):
        raise ValueError("markdown must be a str")
    headings: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    fence: str | None = None  # the opening fence line's run, e.g. "```"
    for line in markdown.split("\n"):
        line = line.removesuffix("\r")
        run = _FENCE.match(line)
        if fence is not None:
            if run and run.group()[0] == fence[0] and len(run.group()) >= len(fence):
                fence = None
            continue
        if run:
            fence = run.group()
            continue
        match = _ATX.fullmatch(line)
        if not match:
            continue
        title = _CLOSING.sub("", (match.group(2) or "").strip()).rstrip()
        if not title:
            continue
        base = _slug(title)
        count = seen.get(base, 0)
        seen[base] = count + 1
        headings.append((len(match.group(1)), title, base))
    return headings


def heading_tree(markdown: str) -> list[dict]:
    roots: list[dict] = []
    stack: list[dict] = []
    for level, title, anchor in extract_headings(markdown):
        node = {"level": level, "title": title, "anchor": anchor, "children": []}
        while stack and stack[-1]["level"] >= level:
            stack.pop()
        (stack[-1]["children"] if stack else roots).append(node)
        stack.append(node)
    return roots
