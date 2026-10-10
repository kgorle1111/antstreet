"""docs/PYPI.md is the PyPI page: no relative links, the caveat stays, no overclaim words."""

import re

from docs_support import DOCS, read

TEXT = read(DOCS / "PYPI.md")
BANNED = ("prove", "verified", "tamper-proof", "catches", "beats")


def test_every_link_and_image_is_absolute_https() -> None:
    urls = re.findall(r"\]\(([^)\s]+)\)", TEXT) + re.findall(r'src="([^"]+)"', TEXT)
    assert urls
    assert [u for u in urls if not u.startswith("https://")] == []


def test_caveat_travels_with_the_claim() -> None:
    assert "29 of 77 runs (38%" in TEXT
    assert "17 small Python tasks" in TEXT and "16 of 77 (21%)" in TEXT and "Haiku" in TEXT


def test_no_banned_words() -> None:
    low = TEXT.lower()
    assert [w for w in BANNED if re.search(rf"\b{w}\b", low)] == []
