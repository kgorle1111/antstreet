"""ROADMAP.md, the public plan, stays reachable: it exists, the README links it, and every
relative link in it points at a file in the repository."""

import re

from docs_support import ROOT, read, section

ROADMAP = ROOT / "ROADMAP.md"


def test_the_roadmap_exists_and_the_readme_links_it():
    assert ROADMAP.is_file()
    readme = section(read(ROOT / "README.md"), "🗺️ Where it's going (planned, not built)")
    assert "[ROADMAP.md](ROADMAP.md)" in readme


def test_every_relative_link_in_the_roadmap_resolves():
    refs = re.findall(r"\]\(([^)\s]+)\)", read(ROADMAP))
    local = [r for r in refs if not r.startswith(("http://", "https://", "#", "mailto:"))]
    assert local, "the roadmap links nothing local"
    missing = [r for r in local if not (ROOT / r.partition("#")[0]).exists()]
    assert not missing, f"the roadmap points at nothing: {missing}"


def test_the_roadmap_ids_are_backlog_ids():
    backlog = set(re.findall(r"^\| (B\d+) \|", read(ROOT / "docs" / "BACKLOG.md"), re.M))
    cited = set(re.findall(r"\bB\d{2,3}\b", read(ROADMAP)))
    assert cited and cited <= backlog, f"not in docs/BACKLOG.md: {sorted(cited - backlog)}"
