"""Every number on the site is bound to its source, and its motion respects the reading floor.

- site/src/data/facts.json: each fact's quotes are in their source files, every digit it shows is
  in a quote (or counted, or computed here), B1 and B2 are the pinned literals, each has a caveat.
- site/src/data/grid.json: the 77 cells are the false-pass audit's (29 / 16 / 9 / 4).
- the built page: every digit sits inside a bound fact or a marked literal, every fact it shows has
  its caveat on the page, no banned word appears, and the only seal text is CHECKS PASSED.
- site/src/data/hook.json: each autoplay line is on screen long enough to read.
"""

import json
import os
import re
from collections import Counter
from html import unescape
from html.parser import HTMLParser

import pytest
from docs_support import ROOT, read

DATA = ROOT / "site" / "src" / "data"
AUDIT = ROOT / "bench" / "results" / "2026-10-03-false-pass-audit" / "README.md"
B1 = (
    "29 of 77 runs passed their own checks and failed a hidden one "
    "(16 of 77 under a strict count; 17 small Python tasks; Haiku)"
)
B2 = "9 of the 29 failed only on non-ASCII input"
NUMBER = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
BANNED = [
    r"\bprov(?:e|es|en|ing)\b", r"\bverified\b", r"tamper-proof", r"\bbeats\b",
    r"\bcatch(?:es)? \d+%", r"caught them lying", r"15 of 29",
    r"each one is a real bug", r"\bfirm\b", r"term sheet", r"\binvestors?\b", r"\bboss\b",
]  # fmt: skip
FACTS = json.loads((DATA / "facts.json").read_text())
GRID = json.loads((DATA / "grid.json").read_text())


def flat(text: str) -> str:
    return " ".join(text.split())


# --- facts.json ---------------------------------------------------------------------------------


@pytest.mark.parametrize("fid", sorted(FACTS))
def test_each_fact_is_quoted_from_its_source_and_shows_no_other_number(fid):
    fact = FACTS[fid]
    assert fact["caveat"].strip(), f"{fid} has no caveat"
    assert fact["value"] in fact["wording"], f"{fid}: the value is not in the wording"
    allowed: set[str] = set(fact.get("computed", []))
    for src in fact["sources"]:
        text = read(ROOT / src["path"])
        if "count" in src:
            n = len(re.findall(src["count"], text, re.M))
            assert n == src["equals"], f"{fid}: {src['path']} now has {n}, not {src['equals']}"
            allowed.add(str(n))
        else:
            assert flat(src["quote"]) in flat(text), f"{fid}: {src['path']} lost {src['quote']!r}"
            allowed |= set(NUMBER.findall(src["quote"]))
    shown = NUMBER.findall(fact["wording"] + " " + fact["caveat"] + " " + fact["value"])
    unbound = [n for n in shown if n not in allowed and n.replace(",", "") not in allowed]
    assert not unbound, f"{fid} shows numbers no source gives: {unbound}"


def test_the_binding_strings_are_pinned():
    assert FACTS["b1"]["wording"] == B1
    assert FACTS["b2"]["wording"] == B2
    assert FACTS["b2"]["caveat"] == B1, "B2 never appears without B1 as its caveat"


def test_the_python_facts_are_true_here():
    assert "١٢٣".isdigit() is True
    assert int("١٢٣") == 123
    assert FACTS["isdigit"]["computed"] == ["123"]


# --- grid.json ----------------------------------------------------------------------------------


def audit_cases() -> dict[int, tuple[str, str, int]]:
    runs = {"H": "heldout3", "F": "final3"}
    rows = re.findall(r"^\| (\d+) \| ([HF]) (\w+) r(\d) \|", read(AUDIT), re.M)
    return {int(n): (runs[r], t, int(p)) for n, r, t, p in rows}


def test_the_grid_is_the_audits_77_cells():
    assert [c["cell"] for c in GRID] == list(range(77))
    fp = [c for c in GRID if c["false_pass"]]
    assert len(fp) == 29
    assert sum(not c["strict_drop"] for c in fp) == 16
    drops = Counter(c["strict_drop"] for c in GRID if c["strict_drop"])
    assert drops == {"non-ascii": 9, "int-vs-float": 4}
    assert all(c["strict_drop"] is None for c in GRID if not c["false_pass"])
    assert Counter(c["run"] for c in GRID) == {"heldout3": 41, "final3": 36}
    assert len({(c["run"], c["task"], c["rep"]) for c in GRID}) == 77


def test_every_false_pass_cell_is_its_audit_case():
    cases = audit_cases()
    assert sorted(cases) == list(range(1, 30))
    for c in GRID:
        if c["false_pass"]:
            assert cases[c["case"]] == (c["run"], c["task"], c["rep"]), c
            assert c["hidden_failed"] and c["idea"]
        else:
            assert c["case"] is None and not c["hidden_failed"]


def test_the_grid_matches_the_audits_per_task_counts():
    section = read(AUDIT).split("## Patterns by task", 1)[1].split("\n- ", 1)[0]
    for task, h, f in re.findall(r"^\| (\w+) \| (\d+/\d+) \| (\d+/\d+) \|", section, re.M):
        for run, cell in (("heldout3", h), ("final3", f)):
            fails, total = map(int, cell.split("/"))
            mine = [c for c in GRID if c["task"] == task and c["run"] == run]
            assert (sum(c["false_pass"] for c in mine), len(mine)) == (fails, total), (task, run)


def test_the_strict_drops_are_the_audits_13():
    readme = flat(read(AUDIT))
    assert "9 of the 29 fail only on non-ASCII input and 4 only on an `int`" in readme
    ints = {c["case"] for c in GRID if c["strict_drop"] == "int-vs-float"}
    assert {cases[1] for n, cases in audit_cases().items() if n in ints} == {"tokenbucket"}


# --- hook.json: the reading floor ---------------------------------------------------------------

FRAME_MS = 1000 / 30
ENTRY_MS = 5 * FRAME_MS  # a line enters in 5 frames; it is "settled" after that


def words(text: str) -> int:
    """A numeral counts as two words (DIRECTORS-TREATMENT §4)."""
    return sum(2 if NUMBER.fullmatch(w.strip(".,;:()")) else 1 for w in text.split())


def test_every_autoplay_line_is_on_screen_long_enough_to_read():
    hook = json.loads((DATA / "hook.json").read_text())
    for line in hook["lines"]:
        if line["outMs"] is None:
            continue  # stays once landed
        settled = line["outMs"] - (line["inMs"] + (ENTRY_MS if line["inMs"] else 0))
        need = (15 + 9 * words(line["text"])) * FRAME_MS
        assert settled >= need, f"{line['text']!r} holds {settled:.0f} ms, needs {need:.0f} ms"
    for line in hook["lines"]:
        if "minHoldMs" in line:
            assert line["outMs"] is None or line["outMs"] - line["inMs"] >= line["minHoldMs"]
    beats = hook["beats"]
    assert beats["land"] < beats["cut"] < beats["open"] < beats["settle"] <= 5400


def test_the_reading_floor_lint_can_fail():
    assert words("It wrote its own checks.") == 5 and words("29 of 77 runs") == 6
    short = {"text": "Checks it never saw.", "inMs": 2133, "outMs": 3000}
    settled = short["outMs"] - (short["inMs"] + ENTRY_MS)
    assert settled < (15 + 9 * words(short["text"])) * FRAME_MS


def test_the_hook_sub_is_the_readmes_one_liner():
    hook = json.loads((DATA / "hook.json").read_text())
    sub = next(line["text"] for line in hook["lines"] if line["id"] == "sub")
    assert sub in flat(read(ROOT / "README.md")).replace("**", "")


# --- the built page -----------------------------------------------------------------------------

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


class Page(HTMLParser):
    """Text nodes with the attributes of their ancestors."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict[str, str | None]]] = []
        self.texts: list[tuple[str, list[dict[str, str | None]]]] = []
        self.elements: list[tuple[dict[str, str | None], list[str]]] = []

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        self.stack.append((tag, dict(attrs)))
        self.elements.append((dict(attrs), []))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data):
        if not data.strip() or any(t in ("script", "style", "title") for t, _ in self.stack):
            return
        self.texts.append((data, [a for _, a in self.stack]))


@pytest.fixture(scope="module")
def page() -> tuple[str, Page]:
    built = ROOT / "site" / "dist" / "index.html"
    if not built.is_file():
        if os.environ.get("SITE_DIST_REQUIRED") == "1":
            pytest.fail("site/dist/index.html is missing: run `npm ci && npm run build` in site/")
        pytest.skip("site/dist not built (npm ci && npm run build in site/)")
    parser = Page()
    html = read(built)
    parser.feed(html)
    return html, parser


def visible(parser: Page) -> str:
    return flat(" ".join(t for t, _ in parser.texts))


def test_every_digit_on_the_page_is_a_bound_fact_or_a_marked_literal(page):
    _, parser = page
    loose = []
    for text, ancestors in parser.texts:
        if not re.search(r"[0-9٠-٩]", text):
            continue
        if any("data-fact" in a for a in ancestors):
            continue
        literal = [a for a in ancestors if "data-literal" in a]
        if literal:
            assert not re.search(r"[0-9]\s*%|[0-9]+ of [0-9]", text), (
                f"a claim marked literal: {text!r}"
            )
            continue
        loose.append(text.strip())
    assert not loose, f"numbers on the page with no source: {loose}"


def test_every_bound_fact_shows_its_value_and_its_caveat_is_on_the_page(page):
    html, _ = page
    used = set(re.findall(r'data-fact="([\w-]+)"', html))
    assert used == set(FACTS), f"unused or unknown facts: {used ^ set(FACTS)}"
    text = flat(unescape(re.sub(r"<[^>]+>", " ", html)))
    for fid in used:
        assert re.search(rf'data-fact="{fid}" data-caveat', html), f"{fid}'s caveat is not shown"
        assert flat(FACTS[fid]["caveat"]) in text, fid
    assert B1 in text and B2 in text


def test_no_banned_word_on_the_page_or_in_the_readme_art(page):
    _, parser = page
    texts = [visible(parser)]
    for svg in ("hero.svg", "demo.svg"):
        raw = read(ROOT / "docs" / "assets" / svg)
        texts.append(" ".join(re.findall(r"<text[^>]*>(.*?)</text>", raw)))
    texts += [f["wording"] + " " + f["caveat"] for f in FACTS.values()]
    for t in texts:
        for pattern in BANNED:
            assert not re.search(pattern, t, re.I), f"banned {pattern!r} in: {t[:120]}"


def test_checks_passed_is_the_only_seal_text(page):
    html, _ = page
    assert re.findall(r'class="seal-text"[^>]*>([^<]*)<', html) == ["CHECKS PASSED"]
    for word in ("VERIFIED", "CERTIFIED"):
        assert word not in html.upper()


def test_the_banned_list_catches_what_it_should():
    hits = ["We prove it", "VERIFIED", "it beats X", "catches 40%", "the firm", "boss fund"]
    for h in hits:
        assert any(re.search(p, h, re.I) for p in BANNED), h
    assert not any(re.search(p, "an approved check, verify it", re.I) for p in BANNED)
