"""The Pages site in site/ stays whole: every local link and asset exists, and the copied replay
matches the README's."""

import re

from docs_support import ROOT, read

SITE = ROOT / "site"
PAGE = SITE / "index.html"
PAGES_URL = "https://kgorle1111.github.io/antstreet/"
# The launch video may be absent; story.js keeps its slot hidden until the file is there.
OPTIONAL_VIDEO = "assets/brag.mp4"


def test_every_local_href_and_src_in_the_page_is_a_file_in_site():
    page = read(PAGE)
    refs = re.findall(r'\b(?:href|src|data-src|poster)="([^"]+)"', page)
    # The social card is an absolute URL by necessity; it must still point inside the site.
    refs += [u.removeprefix(PAGES_URL) for u in re.findall(r'content="(https://[^"]+)"', page)]
    local = [r for r in refs if not r.startswith(("http://", "https://", "#", "mailto:"))]
    local = [r for r in local if r not in ("", "./", OPTIONAL_VIDEO)]  # "" and "./" are the root
    assert len(local) >= 5, f"the page links too little that is local: {local}"
    missing = [r for r in local if not (SITE / r).is_file()]
    assert not missing, f"site/index.html points at nothing: {missing}"
    for ref in local:
        assert (SITE / ref).resolve().is_relative_to(SITE.resolve()), f"{ref} leaves site/"


def test_every_in_page_anchor_and_use_target_exists():
    page = read(PAGE)
    ids = set(re.findall(r'\bid="([^"]+)"', page))
    targets = re.findall(r'href="#([^"]+)"', page)
    assert targets, "the page has no in-page links or <use> references"
    assert not set(targets) - ids, f"no element with these ids: {set(targets) - ids}"


def test_the_site_replay_is_the_readme_replay():
    assert (SITE / "assets" / "demo.svg").read_bytes() == (
        ROOT / "docs" / "assets" / "demo.svg"
    ).read_bytes()
