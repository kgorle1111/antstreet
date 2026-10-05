"""README.md, the showcase, stays true: every figure is bound to its source, every image and link
exists, and the SVGs are well-formed, small and show real output."""

import re
import subprocess
import sys
import xml.dom.minidom

import pytest
from docs_support import DOCS, ROOT, read, run_cli

README = ROOT / "README.md"
ASSETS = ROOT / "docs" / "assets"
AUDIT = ROOT / "bench" / "results" / "2026-10-03-false-pass-audit" / "README.md"
BLIND = ROOT / "bench" / "results" / "2026-10-03-blind35" / "table.md"


@pytest.fixture(scope="module")
def text() -> str:
    return " ".join(read(README).split())


def test_the_technical_readme_is_linked_near_the_top():
    head = "\n".join(read(README).splitlines()[:20])
    assert "The full technical tour: [README-technical.md](README-technical.md)" in head
    assert (ROOT / "README-technical.md").is_file()


def test_every_local_link_image_and_anchor_target_exists():
    body = read(README)
    refs = re.findall(r"\]\(([^)\s]+)\)", body) + re.findall(r'(?:src|href)="([^"]+)"', body)
    local = [r for r in refs if not r.startswith(("http://", "https://", "#", "mailto:"))]
    assert local, "the README links nothing local"
    missing = [r for r in local if not (ROOT / r.partition("#")[0]).exists()]
    assert not missing, f"the README points at nothing: {missing}"
    for anchor in re.findall(r"\]\(#([\w-]+)\)", body):
        slug = re.compile(r"^#{1,6} (.+)$", re.M)
        found = {re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", h.lower())) for h in slug.findall(body)}
        assert anchor in found, f"#{anchor} is not a heading in the README"


def test_the_threat_rows_linked_exist():
    model = read(DOCS / "THREAT_MODEL.md")
    for row in re.findall(r"THREAT_MODEL\.md#(t\d+)", read(README)):
        assert f'<a id="{row}"></a>' in model


def test_only_shields_io_is_used_as_an_external_image():
    urls = re.findall(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", read(README))
    assert urls and all(u.startswith("https://img.shields.io/badge/") for u in urls)
    assert not re.search(r'<img[^>]+src="https?://', read(README))


def test_the_false_pass_figures_are_the_audits(text):
    audit = " ".join(read(AUDIT).split())
    for fact in ("29 false-pass cells", "29 of 77 (37.7%, Wilson 95% [28-49%])", "16 of 77 (20.8%"):
        assert fact in audit, f"the audit lost: {fact}"
    assert "widens the 38% interval to 20-57%" in audit
    assert "9 of the 29 fail only on non-ASCII input and 4 only on an `int`" in audit  # 9 + 4 = 13
    for phrase in (
        "29 of 77 runs (38%, 95% interval 28-49%)",
        "(resampling tasks widens the interval to 20-57%)",
        "17 small Python tasks, Haiku writing both the checks and the code",
        "13 of the 29 failed only on non-ASCII input or a returned type",
        "16 of 77 (21%)",
        "Every one of the 29 was a real error against the task text",
    ):
        assert phrase in text, f"README lost: {phrase}"


def test_the_blinded_benchmark_figures_are_the_runs_table(text):
    rows = {
        line.split("|")[1].strip(): [c.strip() for c in line.strip().strip("|").split("|")]
        for line in read(BLIND).splitlines()
        if line.startswith("| ")
    }
    single, firm = rows["single"], rows["firm"]
    assert (firm[1], firm[3], firm[4], firm[6]) == ("105", "64", "61% [51-70%]", "$0.2149")
    assert (single[1], single[3], single[4], single[6]) == ("105", "62", "59% [49-68%]", "$0.0883")
    assert round(0.2149 / 0.0883, 1) == 2.4
    assert "| AntStreet (boss + ants) | 64 of 105 (61%) | $0.2149 |" in text
    assert "| one agent | 62 of 105 (59%) | $0.0883 |" in text
    for phrase in (
        "35 tasks, three runs each, $0.40 a task",
        "the difference is not shown, and the firm cost about 2.4 times as much",
    ):
        assert phrase in text, f"README lost: {phrase}"
    assert "35 of 51" not in text, (
        "the unblinded run is not comparable; the showcase must not cite it"
    )


def test_the_test_count_floor_is_true():
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "--co", "-q", "-m", "slow or not slow"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    collected = int(re.search(r"(\d+) tests? collected", out).group(1))  # type: ignore[union-attr]
    assert collected >= 5000
    body = read(README)
    assert "tests-5000%2B-brightgreen" in body and "**5,000+ tests**" in body


def test_the_engineering_figures_are_the_repos(text):
    ci = read(ROOT / ".github" / "workflows" / "ci.yml")
    assert ci.count("--fail-under=96") == 2 and "98.58%" in ci
    assert "**Coverage floor 96%**" in text and "about 98% measured" in text
    assert re.search(r"^strict = true", read(ROOT / "pyproject.toml"), re.M)
    assert "`mypy --strict`" in text and "typed-mypy%20strict" in text
    threats = re.findall(r"^\| T(\d+) ", read(DOCS / "THREAT_MODEL.md"), re.M)
    assert len(threats) == 69 and "A threat model with 69 rows" in text
    decisions = re.findall(r"^### D\d+:", read(DOCS / "DECISIONS.md"), re.M)
    assert len(decisions) == 45 and "**45 recorded design decisions**" in text
    experiments = re.findall(r"^## E\d+\. ", read(ROOT / "bench" / "PREREG.md"), re.M)
    assert len(experiments) == 6 and "six experiments fixed before any run" in text
    assert "macOS seatbelt; Linux `bwrap`, run and required in CI" in text
    assert "Python 3.12+" in text and "python-3.12%2B" in text
    assert "license-Apache--2.0" in text
    assert "Apache License, Version 2.0" in read(ROOT / "LICENSE")
    assert "Built, not yet installable: a Claude Code plugin" in read(ROOT / "README-technical.md")
    assert "(planned, not built)" in text


def test_the_showcase_has_its_sections():
    heads = re.findall(r"^## (.+)$", read(README), re.M)
    assert [h.split(" ", 1)[1] for h in heads] == [
        "The one-minute pitch",
        "See it run",
        "The problem",
        'We measure, and we publish the "no"',
        "How it flows",
        "Why it is different",
        "How it's engineered",
        "Quickstart",
        "Status and honest limits",
        "Roadmap (planned, not built)",
        "Contributing",
        "License",
    ]
    assert "```mermaid" in read(README)


@pytest.mark.parametrize(
    "name", ["hero.svg", "demo.svg", "mascot-pig.svg", "mascot-bull.svg", "mascot-ant.svg"]
)
def test_each_svg_is_well_formed_small_and_scriptless(name):
    path = ASSETS / name
    assert path.stat().st_size < 60_000
    dom = xml.dom.minidom.parse(str(path))
    assert dom.documentElement.tagName == "svg"
    raw = read(path).lower()
    for banned in ("<script", "onload=", "javascript:", "http://", "https://", "@import", "<image"):
        if banned == "http://":
            raw = raw.replace("http://www.w3.org/2000/svg", "")
        assert banned not in raw, f"{name} contains {banned}"


def test_the_name_is_one_plain_text_element_in_the_hero():
    hero = read(ASSETS / "hero.svg")
    assert len(re.findall(r">AntStreet</text>", hero)) == 1
    assert "Your AI agents get paid when the checks pass." in hero


def test_the_demo_shows_only_strings_a_real_run_prints(tmp_path):
    code, _, said = run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"])
    assert code == 0
    printed = "\n".join(said)
    demo = read(ASSETS / "demo.svg")
    import html

    shown = [html.unescape(t) for t in re.findall(r"<text[^>]*>([^<]*)</text>", demo)]
    real = [t for t in shown if t.strip() and not t.startswith(("$", "replay of", "spend (CLI"))]
    assert len(real) >= 15
    for line in real:
        if line.startswith("boss fund"):
            assert line == 'boss fund "Reverse a string." --budget 0.50'
        elif line.startswith("[a]pprove"):
            prompt = "[a]pprove, [r]eject, or [e]dit files and re-check? "
            assert line == prompt + "a" and f'ask("{prompt}")' in read(
                ROOT / "src/boss/approval.py"
            )
        else:
            assert line.strip() in printed, f"the demo shows output a run does not print: {line!r}"
    for spend in ("boss $0.0040", "worker:w1 $0.0060", "total $0.0100"):
        assert spend in demo
        assert spend in " ".join(printed.split())
    assert "replay of a test-suite run (fake model), not a live recording" in demo
