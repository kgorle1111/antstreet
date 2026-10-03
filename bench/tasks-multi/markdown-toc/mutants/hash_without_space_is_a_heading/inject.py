# Same as the reference; the bug is in headings.py: A line like '#hashtag' is accepted as a
# heading because the space after the hashes is optional.
from headings import extract_headings, fenced_lines
from toc import render_toc

START = "<!-- toc -->"
END = "<!-- /toc -->"


def find_markers(markdown):
    fenced = fenced_lines(markdown)
    lines = markdown.split("\n")
    starts = [i for i, line in enumerate(lines) if i + 1 not in fenced and line.strip() == START]
    ends = [i for i, line in enumerate(lines) if i + 1 not in fenced and line.strip() == END]
    if len(starts) != 1 or len(ends) != 1:
        raise ValueError("need exactly one start marker and one end marker")
    if starts[0] > ends[0]:
        raise ValueError("the start marker must come before the end marker")
    return starts[0], ends[0]


def update_toc(markdown, min_level=1, max_level=6):
    start, end = find_markers(markdown)
    lines = markdown.split("\n")
    outside = "\n".join(lines[: start + 1] + lines[end:])
    toc = render_toc(extract_headings(outside), min_level, max_level)
    body = [""] + (toc.splitlines() + [""] if toc else [])
    return "\n".join(lines[: start + 1] + body + lines[end:])
