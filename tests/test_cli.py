"""CLI tests. `boss fund` runs end to end against a fake `claude` that plays boss and worker."""

import json
import sys

import pytest

from boss.cli import EXIT_FAILED, EXIT_INCOMPLETE, EXIT_OK, EXIT_USAGE, main
from boss.ledger import EventType, read_events, total

CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
INIT = {
    "type": "system",
    "subtype": "init",
    "tools": ["Read", "Write", "Edit", "StructuredOutput"],
    "mcp_servers": [],
    "permissionMode": "dontAsk",
    "claude_code_version": "2.1.285",
    "session_id": "s-1",
}
USAGE = {"m": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}}
FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, sys
argv = sys.argv[1:]
say = lambda e: print(json.dumps(e), flush=True)
result = {{"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "modelUsage": {USAGE!r}, "session_id": "s-1"}}
if argv[argv.index("--output-format") + 1] == "json":   # the boss drafting a term sheet
    thinking = os.environ.get("MAX_THINKING_TOKENS", "unset")
    open(os.path.join(os.environ["HOME"], "boss_thinking.txt"), "w").write(thinking)
    say(result | {{"total_cost_usd": 0.004, "structured_output": {DRAFT!r}}})
else:                                                    # a worker slice
    say({INIT!r})
    override = os.path.join(os.environ["HOME"], "fake_product.py")  # env vars are stripped
    code = "def reverse(s):\\n    return s[::-1]\\n"
    if os.path.exists(override):
        code = open(override).read()
    if os.environ.get("FAKE_BREAK"):  # only visible if the caller's environment leaks through
        code = "broken ="
    open("rev.py", "w").write(code)
    say(result | {{"total_cost_usd": 0.006,
                  "structured_output": {{"status": "done", "reason": "wrote rev.py"}}}})
"""


@pytest.fixture
def boss(tmp_path):
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    project = tmp_path / "project"
    project.mkdir()

    def run(*argv, answers=("a",), **env):
        said, replies = [], iter(answers)
        environ = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "BOSS_CLAUDE_BIN": str(fake),
            **env,
        }
        code = main(
            [*argv, "--dir", str(project)],
            ask=lambda prompt: next(replies),
            say=said.append,
            environ=environ,
        )
        return code, "\n".join(said)

    run.project = project
    run.runs = lambda: sorted((project / ".boss" / "runs").iterdir())
    return run


def test_fund_builds_the_idea_and_reports_from_the_ledger(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    assert code == EXIT_OK
    assert "Round 1: 1/1 checks passed, next round unlocked" in output
    [run_dir] = boss.runs()
    events = read_events(run_dir / "ledger.jsonl")
    assert [e.event for e in events] == [
        EventType.BOSS_CALL,
        EventType.APPROVED,
        EventType.HIRED,
        EventType.SLICE_START,
        EventType.SLICE_END,
        EventType.CHECK_RESULT,
        EventType.ROUND_CLOSED,
    ]
    assert total(events).cost_micros == 4_000 + 6_000
    assert "total        $0.0100" in (run_dir / "report.md").read_text()
    assert json.loads((run_dir / "term_sheet.json").read_text())["approved_by_investor"] is True
    assert (run_dir / "workspaces" / "w1" / "rev.py").is_file()


def test_rejecting_the_term_sheet_spends_nothing_on_workers(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", answers=("r",))
    assert code == EXIT_FAILED
    assert "Rejected. Nothing was funded." in output
    events = read_events(boss.runs()[0] / "ledger.jsonl")
    assert [e.event for e in events] == [EventType.BOSS_CALL, EventType.STOPPED]
    assert not (boss.runs()[0] / "workspaces").exists()


def test_failing_work_exits_incomplete(boss):
    (boss.project.parent / "fake_product.py").write_text("def reverse(s):\n    return s\n")
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    assert code == EXIT_INCOMPLETE
    assert "Round 1: 0/1 checks passed, not unlocked" in output


def test_callers_environment_does_not_reach_the_worker(boss):
    # The fake writes a broken product if it can see this variable; the allowlist must drop it.
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.50", FAKE_BREAK="1")
    assert code == EXIT_OK


def test_report_and_status_read_the_latest_run(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50")
    code, report = boss("report")
    assert code == EXIT_OK and "BOARD REPORT" in report
    code, status = boss("status")
    assert code == EXIT_OK
    assert "last event boss round_closed; 1/1 checks passing; spend $0.0100 estimated" in status


def test_report_without_runs_or_with_an_unknown_run(boss):
    code, output = boss("report")
    assert code == EXIT_FAILED and "No runs under" in output
    boss("fund", "Reverse a string.", "--budget", "0.50")
    code, output = boss("report", "nope")
    assert code == EXIT_FAILED and "No run 'nope'" in output


@pytest.mark.parametrize("budget", ["0", "-1", "abc", "0.0000001"])
def test_bad_budget_is_a_usage_error(boss, budget, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "x", "--budget", budget)
    assert info.value.code == 2
    assert "budget" in capsys.readouterr().err


def test_a_budget_too_small_for_one_slice_is_refused_before_anything_is_spent(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.104999")
    assert code == EXIT_USAGE
    assert "cannot fund one worker slice" in output and "at least $0.105" in output
    assert not (boss.project / ".boss").exists()  # no run folder, no boss call, no ledger


def test_the_budget_check_is_per_round(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.20", "--rounds", "2")
    assert code == EXIT_USAGE and "over 2 round(s)" in output
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.21", "--rounds", "2")
    assert code == EXIT_OK


def test_reserve_option_reaches_the_slice_cap(boss):
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.05", "--reserve", "0.01")
    assert code == EXIT_OK
    [start] = [e for e in read_events(boss.runs()[0] / "ledger.jsonl") if e.event == "slice_start"]
    assert start.data["cap_micros"] == 40_000  # 0.05 budget - 0.01 reserve, under the 0.10 slice


def test_boss_thinking_option_reaches_the_boss_call_and_the_ledger(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50", "--boss-thinking", "0")
    assert (boss.project.parent / "boss_thinking.txt").read_text() == "0"
    [call] = [e for e in read_events(boss.runs()[0] / "ledger.jsonl") if e.event == "boss_call"]
    assert call.data["thinking_tokens"] == 0
    boss("fund", "Reverse a string.", "--budget", "0.50")
    assert (boss.project.parent / "boss_thinking.txt").read_text() == "unset"


@pytest.mark.parametrize("bad", ["-1", "1.5", "lots"])
def test_bad_boss_thinking_is_a_usage_error(boss, bad, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "x", "--budget", "0.50", "--boss-thinking", bad)
    assert info.value.code == 2
    assert "whole number of tokens" in capsys.readouterr().err


def test_max_minutes_stops_the_run_and_the_report_says_why(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", "--max-minutes", "1e-9")
    assert code == EXIT_INCOMPLETE
    assert "Ended early: stopped:" in output and "wall clock elapsed; the run limit is" in output
    events = read_events(boss.runs()[0] / "ledger.jsonl")
    assert [e for e in events if e.event == "slice_start"] == []  # stopped before any spend


@pytest.mark.parametrize("bad", ["0", "-5", "soon", "inf", "nan"])
def test_bad_max_minutes_is_a_usage_error(boss, bad, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "x", "--budget", "0.50", "--max-minutes", bad)
    assert info.value.code == 2
    assert "positive number of minutes" in capsys.readouterr().err


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert all(command in out for command in ("fund", "report", "status", "doctor"))


def test_doctor_reports_failures_with_a_nonzero_exit(boss):
    code, output = boss("doctor", BOSS_CLAUDE_BIN="/nonexistent/claude")
    assert code == EXIT_FAILED
    assert "FAIL  claude cli" in output and "fix:" in output
