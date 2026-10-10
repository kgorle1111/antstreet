"""The Pages site in site/ (an Astro project) stays whole: every local link and asset in the built
page exists, every in-page anchor has a target, the copied replay matches the README's, and the
Pages workflow builds the site instead of uploading the source.

The built-page tests need `npm ci && npm run build` in site/ first. Without site/dist they skip,
unless SITE_DIST_REQUIRED=1 (the site workflow sets it), where a missing build is a failure."""

import os
import re

import pytest
from docs_support import ROOT, read

SITE = ROOT / "site"
DIST = SITE / "dist"
BASE = "/antstreet/"
PAGES_URL = "https://kgorle1111.github.io/antstreet/"


@pytest.fixture(scope="module")
def built() -> str:
    page = DIST / "index.html"
    if not page.is_file():
        if os.environ.get("SITE_DIST_REQUIRED") == "1":
            pytest.fail("site/dist/index.html is missing: run `npm ci && npm run build` in site/")
        pytest.skip("site/dist not built (npm ci && npm run build in site/)")
    return read(page)


def test_every_local_href_and_src_in_the_built_page_is_a_file(built):
    refs = re.findall(r'\b(?:href|src|data-src|poster)="([^"]+)"', built)
    # The social card is an absolute URL by necessity; it must still point inside the site.
    refs += [
        BASE + u.removeprefix(PAGES_URL) for u in re.findall(r'content="(https://[^"]+)"', built)
    ]
    local = [r for r in refs if not r.startswith(("http://", "https://", "#", "mailto:"))]
    assert len(local) >= 6, f"the page links too little that is local: {local}"
    off_base = [r for r in local if not r.startswith(BASE)]
    assert not off_base, f"these would break under the Pages base path {BASE}: {off_base}"
    files = [DIST / (r.removeprefix(BASE) or "index.html") for r in local]
    missing = [r for r, f in zip(local, files, strict=True) if not f.is_file()]
    assert not missing, f"site/dist/index.html points at nothing: {missing}"
    for ref in local:
        assert (DIST / ref.removeprefix(BASE)).resolve().is_relative_to(DIST.resolve())


def test_the_inlined_css_font_urls_resolve(built):
    fonts = re.findall(r'url\("?(fonts/[^")]+)"?\)', built)
    assert len(fonts) == 4
    assert all((DIST / f).is_file() for f in fonts)


def test_every_in_page_anchor_and_use_target_exists(built):
    ids = set(re.findall(r'\bid="([^"]+)"', built))
    targets = re.findall(r'href="#([^"]+)"', built) + re.findall(r"url\(#([\w-]+)\)", built)
    assert targets, "the page has no in-page links or <use> references"
    assert not set(targets) - ids, f"no element with these ids: {set(targets) - ids}"


def test_no_third_party_requests(built):
    """Only links may leave the site; nothing it loads may (no fonts, scripts or trackers)."""
    tags = re.findall(r"<(?:script|img|link|iframe|source|video)\b[^>]*>", built)
    loads = [t for t in tags if re.search(r'\b(?:src|href)="https?://', t)]
    assert [t for t in loads if 'rel="canonical"' not in t] == []


def test_the_source_has_the_public_assets_the_page_names():
    for name in ("demo.svg", "favicon.svg", "og.png"):
        assert (SITE / "public" / "assets" / name).is_file()
    assert (SITE / ".nvmrc").read_text().strip() == "22"


def test_the_site_replay_is_the_readme_replay():
    assert (SITE / "public" / "assets" / "demo.svg").read_bytes() == (
        ROOT / "docs" / "assets" / "demo.svg"
    ).read_bytes()


def test_pages_builds_the_site_and_uploads_dist():
    flow = read(ROOT / ".github" / "workflows" / "pages.yml")
    for step in (
        "node-version-file: site/.nvmrc",
        "cache-dependency-path: site/package-lock.json",
        "npm ci --ignore-scripts",
        "npm run build",
        "path: site/dist",
    ):
        assert step in flow, f"pages.yml lost: {step}"
    assert '"docs/assets/demo.svg"' in flow


def test_site_checks_run_only_for_site_changes():
    flow = read(ROOT / ".github" / "workflows" / "site.yml")
    assert re.search(r"pull_request:\n\s+paths:\n\s+- \"site/\*\*\"", flow)
    assert 'SITE_DIST_REQUIRED: "1"' in flow and "npx playwright test" in flow
    # actions are pinned the way ci.yml pins them: by major tag
    ci_uses = set(
        re.findall(r"uses: (actions/[\w-]+)@(v\d+)", read(ROOT / ".github/workflows/ci.yml"))
    )
    for action, tag in re.findall(r"uses: (actions/[\w-]+)@(v\d+)", flow):
        same = [t for a, t in ci_uses if a == action]
        assert not same or tag in same, f"{action}@{tag} differs from ci.yml's {same}"
