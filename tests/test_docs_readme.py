"""README.md stays true; every relative link in it and in the documents points at a real file."""

import re

import pytest
from docs_support import (
    DOCS,
    ROOT,
    expected_default,
    read,
    run_cli,
    section,
    table,
)

from boss import budget, cli, worker
from boss.bench.tasks import load_tasks
from boss.ledger import EventType, read_events, total

README = ROOT / "README.md"
LINKED = [
    README,
    ROOT / "CHANGELOG.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "bench" / "METHOD.md",
    *sorted(DOCS.glob("*.md")),
]
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```.*?^```", re.M | re.S)


@pytest.fixture(scope="module")
def text() -> str:
    return read(README)


def slug(heading: str) -> str:
    """The anchor GitHub gives a heading."""
    kept = re.sub(r"[^\w\s-]", "", heading.lower().replace("`", ""))
    return re.sub(r"\s", "-", kept.strip())


def anchors(path) -> set[str]:
    body = FENCE.sub("", read(path))
    found = {slug(m.group(1)) for m in re.finditer(r"^#{1,6} (.+)$", body, re.M)}
    return found | set(re.findall(r'<a id="([\w-]+)"></a>', body))  # a table row's anchor


def broken_links(path, root=ROOT) -> list[str]:
    problems = []
    for link in LINK.findall(FENCE.sub("", read(path))):
        if link.startswith(("http://", "https://", "mailto:")):
            continue
        target, _, anchor = link.partition("#")
        found = (path.parent / target).resolve() if target else path
        if not found.exists():
            problems.append(f"{path.relative_to(root)}: {link} points at nothing")
        elif anchor and found.suffix == ".md" and anchor not in anchors(found):
            problems.append(f"{path.relative_to(root)}: {link} has no such heading")
    return problems


def test_every_relative_link_in_the_readme_and_the_documents_points_at_a_real_target():
    problems = [p for path in LINKED for p in broken_links(path)]
    assert not problems, "\n".join(problems)


def test_the_link_checker_can_fail(tmp_path):
    (tmp_path / "there.md").write_text("# A heading\n")
    doc = tmp_path / "doc.md"
    doc.write_text("[ok](there.md#a-heading) [gone](gone.md) [no anchor](there.md#nope)\n")
    found = broken_links(doc, tmp_path)
    assert len(found) == 2 and "gone.md" in found[0] and "#nope" in found[1]


def test_the_limits_section_links_the_threat_rows_it_is_about(text):
    body = section(text, "Limits")
    linked = set(re.findall(r"THREAT_MODEL\.md#(t\d+)", body))
    assert linked == {"t12", "t13", "t14", "t29", "t39", "t44"}  # broken ones fail the link check


def test_a_threat_row_anchor_counts_as_a_heading(tmp_path):
    (tmp_path / "there.md").write_text('| T9 | <a id="t9"></a>A row |\n')
    doc = tmp_path / "doc.md"
    doc.write_text("[ok](there.md#t9) [no](there.md#t8)\n")
    assert len(broken_links(doc, tmp_path)) == 1


def test_the_documentation_section_links_every_document(text):
    body = section(text, "Documentation")
    linked = set(LINK.findall(body))
    expected = {f"docs/{p.name}" for p in DOCS.glob("*.md")}
    expected |= {"bench/METHOD.md", "CHANGELOG.md", "SECURITY.md", "CONTRIBUTING.md"}
    assert expected <= linked, f"the README does not link: {sorted(expected - linked)}"


def test_the_options_table_agrees_with_the_fund_parser(text):
    fund = cli._parser()._subparsers._group_actions[0].choices["fund"]
    real = {a.option_strings[-1]: a for a in fund._actions if a.option_strings}
    rows = table(section(text, "Use").split("Useful options")[1])
    for row in rows:
        named = re.findall(r"`(--[a-z-]+)", row[0])
        defaults = [d.strip().lstrip("$") for d in row[2].split(",")]
        assert len(named) == len(defaults), f"{row[0]}: one default per option"
        for option, shown in zip(named, defaults, strict=True):
            assert option in real, f"README names {option}, which boss fund does not have"
            want = expected_default(real[option])
            assert want is None or shown == want.lstrip("$"), (
                f"{option}: README {shown}, code {want}"
            )


def test_the_stated_requirements_are_the_enforced_ones(text):
    body = section(text, "Requirements")
    assert (
        f"Claude Code](https://code.claude.com) {'.'.join(map(str, worker.MIN_CLI_VERSION))}"
        in body
    )
    assert "Python 3.12+" in body


def test_the_exit_codes_stated_are_the_constants(text):
    line = " ".join(text[text.index("Exit codes:") :].split("\n\n")[0].split())
    codes = re.findall(r"`(\d+)`", line)
    assert codes == [
        str(c)
        for c in (
            cli.EXIT_OK,
            cli.EXIT_FAILED,
            cli.EXIT_USAGE,
            cli.EXIT_INCOMPLETE,
            cli.EXIT_INTERRUPTED,
        )
    ]


def test_every_command_is_shown_in_the_readme(text):
    for name in cli._parser()._subparsers._group_actions[0].choices:
        assert f"boss {name}" in text, f"the README never shows `boss {name}`"


def test_the_benchmark_figures_agree_with_the_blinded_runs_table_and_the_task_count(text):
    status = " ".join(text.split("## How it works")[0].split())
    table = read(ROOT / "bench" / "results" / "2026-10-03-blind35" / "table.md")
    rows = {
        line.split("|")[1].strip(): line for line in table.splitlines() if line.startswith("| ")
    }
    ran = [
        r for r, line in rows.items() if re.fullmatch(r"\| \S+ \| \d/3 \| \d/3 \|", line.strip())
    ]
    known = {t.id for t in load_tasks(ROOT / "bench" / "tasks")}
    assert set(ran) <= known, f"the results table names tasks that do not exist: {set(ran) - known}"
    assert f"{len(ran)}-task benchmark" in status and len(ran) == 35
    assert rows["single"].startswith("| single | 105 | 35 | 62 | 59% [49-68%] | 92% | $0.0883 |")
    assert rows["firm"].startswith("| firm | 105 | 35 | 64 | 61% [51-70%] | 92% | $0.2149 |")
    assert "| 1m25s |" in rows["single"] and "| 3m34s |" in rows["firm"]
    # Each figure bound to its arm, firm first, so swapping the two arms fails.
    for phrase in (
        "firm passed 64 of 105 (61%) against 62 of 105 (59%) for a single agent",
        "($0.2149 against $0.0883 a task)",
        "(median 3m34s against 1m25s)",
    ):
        assert phrase in status, f"README lost: {phrase}"


def test_the_unblinded_figures_are_only_stated_as_not_comparable(text):
    # The 17-task run gave the single arm an instruction about hidden checks the firm did not get.
    status = " ".join(text.split("## How it works")[0].split())
    assert "(firm 35 of 51, 69%; single 32 of 51, 63%) is not comparable" in status
    assert text.count("35 of 51") == 1 and text.count("69%") == 1


def test_the_roles_table_names_the_roles_the_architecture_defines(text):
    readme = {r[0] for r in table(section(text, "How it works"))}
    architecture = {r[0] for r in table(section(read(DOCS / "ARCHITECTURE.md"), "Roles"))}
    assert readme == architecture


def test_the_run_folder_paths_stated_exist_after_a_run(text, tmp_path):
    code, run_dir, _ = run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"])
    assert code == cli.EXIT_OK
    assert "`.boss/runs/<run>/workspaces/w1/`" in text and (run_dir / "workspaces" / "w1").is_dir()
    assert "`.boss/runs/<run>/product/`" in text and (run_dir / "product").is_dir()
    assert (run_dir / "report.md").is_file()


def test_the_boss_call_is_charged_on_top_of_the_budget(text, tmp_path):
    _, run_dir, _ = run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"])
    events = read_events(run_dir / "ledger.jsonl")
    [call] = [e for e in events if e.event is EventType.BOSS_CALL]
    assert call.round == 0 and call.cost_micros
    in_rounds = budget.round_spend(events, 1).cost_micros
    assert in_rounds == total(events).cost_micros - call.cost_micros
    assert "drafting call is charged on top" in text
