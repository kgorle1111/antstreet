"""docs/CLI.md stays true: every option, default, exit code, environment variable and folder."""

import argparse
import re

import pytest
from docs_support import (
    DOCS,
    ROOT,
    captured_parser,
    expected_default,
    fake_claude,
    read,
    run_cli,
    section,
    table,
)

from boss import cli, worker
from boss.bench import replay
from boss.bench import run as bench_run
from boss.bench import table as bench_table
from boss.bench.tasks import BenchTask
from boss.ledger import EventType, read_events

DOC = DOCS / "CLI.md"
SRC = ROOT / "src" / "boss"
HELP = {"-h", "--help"}
# flags of the `claude` CLI that the document names when it explains isolation
CLAUDE_FLAGS = {"--bare", "--safe-mode"}


@pytest.fixture(scope="module")
def parsers() -> dict[str, argparse.ArgumentParser]:
    """Every documented command, by the name used in the document's headings."""
    top = cli._parser()
    found = {"boss": top}
    found |= {f"boss {name}": p for name, p in top._subparsers._group_actions[0].choices.items()}
    return found


@pytest.fixture(scope="module")
def bench_parsers() -> dict[str, argparse.ArgumentParser]:
    return {
        "python -m boss.bench.run": captured_parser(bench_run.main),
        "python -m boss.bench.table": captured_parser(bench_table.main),
        "python -m boss.bench.replay": captured_parser(replay.main),
    }


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def options(parser: argparse.ArgumentParser) -> dict[str, argparse.Action]:
    return {
        a.option_strings[-1]: a
        for a in parser._actions
        if a.option_strings and not set(a.option_strings) & HELP
    }


def positionals(parser: argparse.ArgumentParser) -> list[str]:
    return [
        a.dest
        for a in parser._actions
        if not a.option_strings and not isinstance(a, argparse._SubParsersAction)
    ]


def all_parsers(parsers, bench_parsers):
    return {**parsers, **bench_parsers}


def test_every_option_of_every_command_is_documented_with_its_default(text, parsers, bench_parsers):
    problems = []
    for name, parser in all_parsers(parsers, bench_parsers).items():
        body = section(text, f"`{name}`")
        rows = {r[0].strip("`"): r for r in table(body)}
        real = options(parser)
        for option in sorted(set(real) - set(rows)):
            problems.append(f"{name}: option {option} is not documented")
        for option in sorted(set(rows) - set(real)):
            problems.append(f"{name}: documents {option}, which the parser does not have")
        for option, action in real.items():
            want = expected_default(action)
            if option in rows and want is not None and rows[option][1].strip("`") != want:
                problems.append(f"{name} {option}: default is {want!r}, doc says {rows[option][1]}")
        for dest in positionals(parser):
            if f"`{dest}`" not in body:
                problems.append(f"{name}: argument {dest} is not documented")
    assert not problems, "\n".join(problems)


def test_every_subcommand_is_documented_and_no_other_is(text, parsers):
    documented = set(re.findall(r"^## `(boss \w+)`\s*$", text, re.M))
    assert documented == {n for n in parsers if n != "boss"}


def test_every_option_named_anywhere_in_the_document_exists_in_some_parser(
    text, parsers, bench_parsers
):
    known = set(HELP) | CLAUDE_FLAGS
    for parser in all_parsers(parsers, bench_parsers).values():
        known |= {s for a in parser._actions for s in a.option_strings}
    mentioned = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]*)", text))
    assert mentioned - known == set(), (
        f"named in the document but not in any parser: {mentioned - known}"
    )


def test_exit_codes_in_the_document_are_the_constants_in_the_code(text):
    body = section(text, "Exit codes of `boss`")
    codes = {r[0].strip("`") for r in table(body)}
    assert codes == {
        str(c) for c in (cli.EXIT_OK, cli.EXIT_FAILED, cli.EXIT_USAGE, cli.EXIT_INCOMPLETE)
    }


def source_env_names() -> set[str]:
    names = set()
    for path in SRC.rglob("*.py"):
        names |= set(
            re.findall(r'(?:environ(?:\.get)?[(\[]|getenv\()\s*"([A-Z][A-Z_]+)"', read(path))
        )
    return names


def test_environment_variables_documented_are_the_ones_the_code_reads(text):
    rows = {r[0].strip("`"): r for r in table(section(text, "Environment variables"))}
    expected = {
        cli.EXECUTABLE_VAR,
        worker._API_KEY_VAR,
        worker._THINKING_VAR,
        *worker._ENV_ALLOWLIST,
        "BOSS_LIVE",
    }
    assert set(rows) == expected
    assert 'os.environ.get("BOSS_LIVE")' in read(ROOT / "tests" / "test_end_to_end.py")
    assert source_env_names() <= expected, "the source reads a variable this document omits"
    readers = {p.relative_to(SRC).as_posix() for p in SRC.rglob("*.py") if "os.environ" in read(p)}
    assert readers == {"cli.py", "bench/run.py"}


@pytest.fixture(scope="module")
def happy(tmp_path_factory):
    folder = tmp_path_factory.mktemp("happy")
    code, run_dir, said = run_cli(folder, ["fund", "Reverse a string.", "--budget", "0.50"])
    return code, run_dir, said


def test_a_run_folder_holds_what_the_document_lists(text, happy):
    code, run_dir, _ = happy
    assert code == cli.EXIT_OK
    assert re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f]{6}", run_dir.name)
    rows = table(section(text, "Run folder"))
    listed = {r[0].strip("`").replace("<worker>", "w1").strip("/") for r in rows}
    for path in listed:
        assert (run_dir / path).exists(), f"documented but not written: {path}"
    assert {p.name for p in run_dir.iterdir()} == {p.split("/")[0] for p in listed}
    assert (run_dir / "checks" / "test_c01.py").is_file()
    assert (run_dir / "product" / "rev.py").is_file()


def test_status_and_report_and_exit_codes_match_the_document(tmp_path, happy):
    project = happy[1].parent.parent.parent
    assert cli.main(["status", "--dir", str(project)], say=lambda _: None) == cli.EXIT_OK
    assert (
        cli.main(["report", "nope", "--dir", str(project)], say=lambda _: None) == cli.EXIT_FAILED
    )
    assert cli.main(["status", "--dir", str(tmp_path)], say=lambda _: None) == cli.EXIT_FAILED


def test_too_small_a_budget_is_a_usage_error_and_spends_nothing(tmp_path):
    code, run_dir, said = run_cli(tmp_path, ["fund", "Reverse a string.", "--budget", "0.05"])
    assert code == cli.EXIT_USAGE and run_dir is None
    assert "$0.105" in " ".join(said)


def test_rejecting_the_term_sheet_exits_one(tmp_path):
    code, _, _ = run_cli(
        tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"], answers=("r",)
    )
    assert code == cli.EXIT_FAILED


def test_a_run_that_ends_with_failing_checks_exits_three_and_says_why(tmp_path):
    code, run_dir, said = run_cli(
        tmp_path, ["fund", "Reverse a string.", "--budget", "0.50"], broken=True
    )
    assert code == cli.EXIT_INCOMPLETE
    assert any(line.startswith("Ended early:") for line in said)
    assert EventType.ROUND_CLOSED in [e.event for e in read_events(run_dir / "ledger.jsonl")]


def test_a_blank_idea_raises_a_value_error_and_leaves_an_empty_run_folder(tmp_path):
    # Documented as not fixed. If this starts failing because the CLI now says something useful,
    # update the note under `boss fund` in docs/CLI.md.
    with pytest.raises(ValueError, match="idea must be non-empty"):
        run_cli(tmp_path, ["fund", " ", "--budget", "0.50"])
    [run_dir] = list((tmp_path / "project" / ".boss" / "runs").iterdir())
    assert (run_dir / "ledger.jsonl").read_text() == ""


def test_doctor_exit_codes(tmp_path):
    binary = str(fake_claude(tmp_path))
    said = []
    project = tmp_path / "p"
    project.mkdir()
    environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": binary}
    assert cli.main(["doctor", "--dir", str(project)], say=said.append, environ=environ) == 0
    missing = environ | {"BOSS_CLAUDE_BIN": str(tmp_path / "nope")}
    assert cli.main(["doctor", "--dir", str(project)], say=said.append, environ=missing) == 1


def test_a_benchmark_cell_folder_holds_what_the_document_lists(text, tmp_path):
    task_dir = tmp_path / "rev"
    (task_dir / "hidden_checks").mkdir(parents=True)
    (task_dir / "reference").mkdir()
    (task_dir / "idea.md").write_text("Create rev.py with reverse(s), returning s reversed.\n")
    (task_dir / "hidden_checks" / "test_reverse.py").write_text(
        "from rev import reverse\n\ndef test_it():\n    assert reverse('abc') == 'cba'\n"
    )
    (task_dir / "reference" / "rev.py").write_text("def reverse(s):\n    return s[::-1]\n")
    task = BenchTask("rev", "reverse", "easy", task_dir)
    environ = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "BOSS_CLAUDE_BIN": str(fake_claude(tmp_path)),
    }
    out = tmp_path / "results"
    for arm in ("single", "firm"):
        result = bench_run.run_cell(
            task, arm, 1, out, environ=environ, set_hash="h", budget_micros=500_000
        )
        assert result.passed, f"{arm}: {result.hidden} {result.outcome}"

    rows = table(section(text, "Benchmark cell folder"))
    for arm in ("single", "firm"):
        cell = out / "rev" / arm / "rep1"
        listed = {r[0].strip("`").strip("/") for r in rows if r[1] in ("both", arm)}
        for path in listed:
            found = list(cell.glob(path.replace("<id>", "*")))
            assert found, f"{arm}: documented but not written: {path}"
        assert {p.name for p in cell.iterdir()} == {p.split("/")[0] for p in listed}
