"""ROADMAP.md, the public plan, stays reachable and current: it exists, the README links it,
every relative link in it points at a file in the repository, and nothing it lists as unbuilt
(Now, Next, and the site's "Up next") is already in the CLI or done in the backlog."""

import argparse
import re

from docs_support import ROOT, read, section

from antstreet import cli

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


def unbuilt() -> str:
    """ROADMAP's "Now" and "Next": work that is not built yet."""
    text = read(ROADMAP)
    return section(text, "Now") + section(text, "Next")


def commands() -> dict[str, argparse.ArgumentParser]:
    """Every command and step the CLI has, as `antstreet audit plan`, with its parser."""
    top = cli._parser()
    found = {}
    for name, parser in top._subparsers._group_actions[0].choices.items():
        found[f"antstreet {name}"] = parser
        if (steps := getattr(parser, "_subparsers", None)) is not None:
            choices = steps._group_actions[0].choices.items()
            found |= {f"antstreet {name} {s}": p for s, p in choices}
    return found


def test_nothing_the_roadmap_lists_as_next_already_exists_in_the_cli():
    # Merged work kept appearing under Now and Next as if unbuilt (PR #78 moved six such items);
    # a command or option the parser already has is shipped, and belongs under Shipped.
    parsers = commands()
    flags = {s for p in parsers.values() for a in p._actions for s in a.option_strings}
    options = flags - {"-h", "--help"}
    built = []
    for span in re.findall(
        r"(?<!existing )`([^`\n]+)`", unbuilt()
    ):  # "the existing `--x`" is a deliberate reference
        words = span.split()
        command = " ".join(words if words[0] == "antstreet" else ["antstreet", *words])
        if span.startswith("-") and words[0] in options or command in parsers:
            built.append(span)
    assert not built, (
        f"listed as unbuilt but already in the CLI: {built}. Move the item to Shipped, or write "
        "'the existing `...`' when an unbuilt item only refers to a built command or option"
    )


def test_the_sites_up_next_lists_only_items_the_roadmap_still_lists():
    def norm(title: str) -> str:
        return re.sub(r"^the ", "", title.replace("`", "").strip().lower())

    roadmap = {norm(t) for t in re.findall(r"^- \*\*(.+?)\*\*", unbuilt(), re.M)}
    page = read(ROOT / "site" / "src" / "components" / "Next.astro")
    site = {norm(t) for t in re.findall(r'^\s*\["([^"]+)",', page, re.M)}
    assert site and site <= roadmap, f"on the site but not under ROADMAP Now/Next: {site - roadmap}"


def test_nothing_the_roadmap_lists_as_next_is_done_in_the_backlog():
    done = set(
        re.findall(r"^\| (B\d+) \|.*\| done\b[^|]*\|\s*$", read(ROOT / "docs" / "BACKLOG.md"), re.M)
    )
    cited = set(re.findall(r"\bB\d{2,3}\b", unbuilt()))
    assert not cited & done, (
        f"listed as unbuilt but done in docs/BACKLOG.md: {sorted(cited & done)}"
    )
