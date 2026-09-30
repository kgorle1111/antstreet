"""Helpers for the tests that keep the documents true. Not a test module."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The body of a `## heading` section, up to the next `## ` heading."""
    match = re.search(rf"^## {re.escape(heading)}\s*$", text, re.M)
    assert match, f"no '## {heading}' heading"
    rest = text[match.end() :]
    end = re.search(r"^## ", rest, re.M)
    return rest[: end.start()] if end else rest


def table(body: str) -> list[list[str]]:
    """Rows of the first markdown table in `body`, header and rule rows excluded."""
    rows: list[list[str]] = []
    for line in body.splitlines():
        if not line.startswith("|"):
            if rows:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows[1:]


def code_spans(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", text)
