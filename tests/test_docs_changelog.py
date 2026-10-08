"""CHANGELOG.md stays true: Keep a Changelog shape, the current version covered, real facts."""

import re
import tomllib

import pytest
from docs_support import ROOT, original_tasks, read

from antstreet import cli, gate, limits
from antstreet.bench.tasks import load_tasks, task_set_hash
from antstreet.ledger import EventType

DOC = ROOT / "CHANGELOG.md"
ALLOWED = {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
RELEASE = re.compile(r"^## \[(Unreleased|\d+\.\d+\.\d+)\](?: - \d{4}-\d{2}-\d{2})?$")
CLAUDE_FLAGS = {"--bare", "--safe-mode"}  # flags of the `claude` CLI, named in the text


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def version() -> str:
    return tomllib.loads(read(ROOT / "pyproject.toml"))["project"]["version"]


def releases(text: str) -> dict[str, dict[str, list[str]]]:
    """Release name -> subsection name -> its lines, in the document."""
    found: dict[str, dict[str, list[str]]] = {}
    release = part = None
    for line in text.splitlines():
        if line.startswith("## "):
            match = RELEASE.match(line)
            assert match, (
                f"a release heading must be '## [Unreleased]' or '## [x.y.z] - date': {line}"
            )
            release, part = match.group(1), None
            found[release] = {}
        elif line.startswith("### "):
            assert release, f"a subsection before any release: {line}"
            part = line[4:].strip()
            found[release][part] = []
        elif part and line.strip():
            found[release][part].append(line)
    return found


def test_the_current_version_has_a_section_or_is_covered_by_unreleased(text):
    found = releases(text)
    assert "Unreleased" in found
    covered = version() in found or f"Version {version()} has not been released" in text
    assert covered, f"pyproject says {version()}: add a section for it or say it is unreleased"


def test_subsection_names_come_from_the_allowed_set_and_are_not_empty(text):
    for release, parts in releases(text).items():
        for name, lines in parts.items():
            assert name in ALLOWED, f"{release}: '{name}' is not one of {sorted(ALLOWED)}"
            assert lines, f"{release}: '{name}' has no entries"


def test_every_entry_is_one_short_bullet(text):
    for release, parts in releases(text).items():
        for name, lines in parts.items():
            entries: list[str] = []
            for line in lines:
                if line.startswith("- "):
                    entries.append(line[2:])
                else:
                    assert line.startswith("  ") and entries, (
                        f"{release}/{name}: stray line: {line}"
                    )
                    entries[-1] += " " + line.strip()
            for entry in entries:
                assert len(entry) <= 260, (
                    f"{release}/{name}: entry is not one line's worth: {entry[:50]}"
                )


def test_sections_are_in_keep_a_changelog_order(text):
    order = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
    for release, parts in releases(text).items():
        seen = [order.index(name) for name in parts]
        assert seen == sorted(seen), f"{release}: sections are out of order"


def test_options_the_changelog_names_exist(text):
    parser = cli._parser()
    known = {s for a in parser._actions for s in a.option_strings} | CLAUDE_FLAGS
    for sub in parser._subparsers._group_actions[0].choices.values():
        known |= {s for a in sub._actions for s in a.option_strings}
        steps = getattr(sub, "_subparsers", None)  # `audit` has steps of its own
        for step in steps._group_actions[0].choices.values() if steps else ():
            known |= {s for a in step._actions for s in a.option_strings}
    named = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", text))
    assert named <= known, f"named in the changelog but not in the CLI: {named - known}"
    commands = set(parser._subparsers._group_actions[0].choices)
    assert set(re.findall(r"`boss (\w+)", text)) <= commands


def test_figures_the_changelog_states_match_the_code_and_the_repository(text):
    run_limits = limits.RunLimits()
    assert f"slices ({run_limits.max_slices})" in text
    assert f"workers ({run_limits.max_workers})" in text
    assert "coverage floor of 96%" in text
    assert "coverage report --show-missing --fail-under=96" in read(
        ROOT / ".github" / "workflows" / "ci.yml"
    )
    tasks = load_tasks(ROOT / "bench" / "tasks")
    assert f"{len(tasks)} tasks" in text
    assert "`c130282a6eec5fe8`" in text and task_set_hash(original_tasks()) == "c130282a6eec5fe8"


def test_the_new_names_and_figures_are_real(text):
    tasks = load_tasks(ROOT / "bench" / "tasks")
    assert f"recall on {sum(len(t.mutants()) for t in tasks)} known-wrong solutions" in text
    events = {e.value for e in EventType}
    for name in ("started", "resumed", "ruled"):
        assert name in events and f"`{name}`" in text
    assert f"`{gate.SANDBOX_ENV}`" in text and f"exits {cli.EXIT_INTERRUPTED}" in text
    assert "(`docs/SANDBOX.md`)" in text and (ROOT / "docs" / "SANDBOX.md").is_file()
    assert "(`docs/BACKLOG.md`)" in text and (ROOT / "docs" / "BACKLOG.md").is_file()
