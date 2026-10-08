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

from antstreet import audit as audit_run
from antstreet import cli, gate, worker
from antstreet.bench import audit, drafts, paired, replay
from antstreet.bench import kpi as bench_kpi
from antstreet.bench import run as bench_run
from antstreet.bench import table as bench_table
from antstreet.bench.tasks import BenchTask
from antstreet.ledger import EventType, read_events
from antstreet.roles import judge

DOC = DOCS / "CLI.md"
SRC = ROOT / "src" / "antstreet"
HELP = {"-h", "--help"}
# flags of the `claude` CLI that the document names when it explains isolation
CLAUDE_FLAGS = {"--bare", "--safe-mode"}


@pytest.fixture(scope="module")
def parsers() -> dict[str, argparse.ArgumentParser]:
    """Every documented command, by the name used in the document's headings."""
    top = cli._parser()
    found = {"boss": top}
    for name, parser in top._subparsers._group_actions[0].choices.items():
        steps = getattr(parser, "_subparsers", None)  # a command with steps of its own: `audit`
        if steps is None:
            found[f"boss {name}"] = parser
        else:
            found |= {f"boss {name} {s}": p for s, p in steps._group_actions[0].choices.items()}
    return found


@pytest.fixture(scope="module")
def bench_parsers() -> dict[str, argparse.ArgumentParser]:
    return {
        "python -m antstreet.bench.run": captured_parser(bench_run.main),
        "python -m antstreet.bench.drafts": captured_parser(drafts.main),
        "python -m antstreet.bench.table": captured_parser(bench_table.main),
        "python -m antstreet.bench.paired": captured_parser(paired.main),
        "python -m antstreet.bench.kpi": captured_parser(bench_kpi.main),
        "python -m antstreet.bench.replay": captured_parser(replay.main),
        "python -m antstreet.bench.audit": captured_parser(audit.main),
    } | {
        f"python -m antstreet.roles.judge {name}": parser
        for name, parser in captured_parser(judge.main)
        ._subparsers._group_actions[0]
        .choices.items()
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
    documented = set(re.findall(r"^## `(boss \w+(?: \w+)?)`\s*$", text, re.M))
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
        str(c)
        for c in (
            cli.EXIT_OK,
            cli.EXIT_FAILED,
            cli.EXIT_USAGE,
            cli.EXIT_INCOMPLETE,
            cli.EXIT_AWAITING,
            cli.EXIT_INTERRUPTED,
        )
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
        audit_run.HOME_VAR,
        worker._API_KEY_VAR,
        worker._THINKING_VAR,
        *worker._ENV_ALLOWLIST,
        gate.SANDBOX_ENV,
        "BOSS_LIVE",
    }
    assert set(rows) == expected
    assert 'os.environ.get("BOSS_LIVE")' in read(ROOT / "tests" / "test_end_to_end.py")
    assert source_env_names() <= expected, "the source reads a variable this document omits"
    readers = {p.relative_to(SRC).as_posix() for p in SRC.rglob("*.py") if "os.environ" in read(p)}
    assert readers == {
        "cli.py",
        "bench/run.py",
        "bench/drafts.py",
        "bench/audit.py",
        "roles/judge.py",
        "gate.py",
        "gitrepo.py",
        "sandbox.py",
    }
    for module in ("gate", "sandbox", "bench.drafts", "bench.audit", "roles.judge"):
        assert f"`antstreet.{module}`" in text


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
    # a run without roles writes the rest; the paths below appear only when a role ran
    listed -= set(ROLE_PATHS)
    listed -= {DISPATCH_PROMPT}  # only a run with --dispatch rules saves the text of each slice
    for path in listed:
        assert (run_dir / path).exists(), f"documented but not written: {path}"
    assert {p.name for p in run_dir.iterdir()} == {p.split("/")[0] for p in listed}
    assert (run_dir / "checks" / "test_c01.py").is_file()
    assert (run_dir / "product" / "rev.py").is_file()


DISPATCH_PROMPT = "logs/w1-s<N>.prompt.txt"


def test_a_dispatch_run_saves_the_text_of_each_slice_where_the_document_says(text, tmp_path):
    argv = ["fund", "Reverse a string.", "--budget", "0.50", "--dispatch", "rules"]
    code, run_dir, _ = run_cli(tmp_path, argv)
    assert code == cli.EXIT_OK
    rows = {r[0].strip("`").replace("<worker>", "w1") for r in table(section(text, "Run folder"))}
    assert DISPATCH_PROMPT in rows
    assert (run_dir / "logs" / "w1-s1.prompt.txt").is_file()


# Path in the document's table -> the path in a run folder, for what only a run with roles writes.
ROLE_PATHS = {
    "stories.json": "stories.json",
    "critic-N": "critic-1",
    "demo": "demo",
    "demo_scratch": "demo_scratch",
}


def test_a_run_with_roles_holds_the_extra_paths_the_document_lists(text, tmp_path):
    import test_pipeline as staged

    tmp_path.mkdir(exist_ok=True)
    fx = staged.Fx(tmp_path)
    staged.every_role(fx)
    assert fx.fund("--roles", "all", answers={"Task": "d"}).code == cli.EXIT_OK
    rows = table(section(text, "Run folder"))
    listed = {r[0].strip("`").replace("<worker>", "w1").strip("/") for r in rows}
    assert set(ROLE_PATHS) <= listed, "a path only roles write is not in the document"
    for documented, real in ROLE_PATHS.items():
        assert (fx.run_dir / real).exists(), f"documented but not written: {documented}"
    for name in ("USAGE.md", "demo.py"):
        assert (fx.run_dir / "demo" / name).is_file()
    assert (fx.run_dir / "critic-1" / "critic_checks").is_dir()
    known = {p.split("/")[0] for p in listed} - set(ROLE_PATHS) | set(ROLE_PATHS.values())
    assert {p.name for p in fx.run_dir.iterdir()} <= known, "a run writes a path nobody documents"


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


def test_a_run_stopped_early_names_the_command_that_continues_it(tmp_path):
    # `--max-minutes` far below the clock's resolution: the limit stops the run before any slice.
    args = ["fund", "Reverse a string.", "--budget", "0.50", "--max-minutes", "1e-9"]
    code, run_dir, said = run_cli(tmp_path, args)
    assert code == cli.EXIT_INCOMPLETE
    assert f"To continue this run: `boss resume {run_dir.name}`" in "\n".join(said)
    code, resumed_dir, said = run_cli(tmp_path, ["resume"])
    assert code == cli.EXIT_INCOMPLETE and resumed_dir == run_dir
    kinds = [e.event for e in read_events(run_dir / "ledger.jsonl")]
    assert kinds.count(EventType.RESUMED) == 1  # the command itself lifts the stop
    assert (run_dir / "report.md").is_file()


def test_resume_with_nothing_to_resume_exits_one_and_spends_nothing(tmp_path):
    code, run_dir, said = run_cli(tmp_path, ["resume"])
    assert code == cli.EXIT_FAILED and run_dir is None
    assert "No runs under" in " ".join(said)


def test_a_count_that_is_not_a_whole_number_is_a_usage_error(tmp_path):
    for option in ("--rounds", "--max-tasks", "--max-slices", "--stall-slices"):
        with pytest.raises(SystemExit) as raised:
            run_cli(tmp_path, ["fund", "x", "--budget", "0.50", option, "0"])
        assert raised.value.code == cli.EXIT_USAGE
    code, run_dir, _ = run_cli(tmp_path, ["fund", "x", "--budget", "0.50", "--slice", "0.001"])
    assert code == cli.EXIT_USAGE and run_dir is None


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


def test_a_blank_idea_is_a_usage_error_and_creates_no_run_folder(tmp_path):
    for idea in (" ", "", " -x"):
        code, run_dir, said = run_cli(tmp_path, ["fund", idea, "--budget", "0.50"])
        assert code == cli.EXIT_USAGE and run_dir is None
        assert "The idea must be some text" in " ".join(said)
    assert not (tmp_path / "project" / ".boss").exists()


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
