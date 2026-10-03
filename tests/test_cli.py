"""CLI tests. `boss fund` runs end to end against a fake `claude` that plays boss and worker."""

import json
import sys

import pytest
from boss_init import BOSS_INIT

import boss.cli as cli_module
from boss.cli import (
    EXIT_FAILED,
    EXIT_INCOMPLETE,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    main,
)
from boss.ledger import EventType, LedgerWriter, read_events, total

CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
TWO_CHECKS = {
    "tasks": DRAFT["tasks"],
    "checks": [
        *DRAFT["checks"],
        {
            "description": "reverses the empty string",
            "task": "t1",
            "code": "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n",
        },
    ],
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
if argv[argv.index("--tools") + 1] == "":   # the boss drafting a term sheet
    say({BOSS_INIT!r})
    thinking = os.environ.get("MAX_THINKING_TOKENS", "unset")
    open(os.path.join(os.environ["HOME"], "boss_thinking.txt"), "w").write(thinking)
    draft = {DRAFT!r}
    if os.path.exists(os.path.join(os.environ["HOME"], "fake_two_checks")):
        draft = {TWO_CHECKS!r}
    say(result | {{"total_cost_usd": 0.004, "structured_output": draft}})
else:                                                    # a worker slice
    say({INIT!r})
    thinking = os.environ.get("MAX_THINKING_TOKENS", "unset")
    open(os.path.join(os.environ["HOME"], "worker_thinking.txt"), "w").write(thinking)
    if os.path.exists(os.path.join(os.environ["HOME"], "fake_interrupt")):
        os.kill(os.getppid(), 2)  # Ctrl-C in the investor's terminal, mid-slice
        import time; time.sleep(30)
    override = os.path.join(os.environ["HOME"], "fake_product.py")  # env vars are stripped
    code = "def reverse(s):\\n    return s[::-1]\\n"
    if os.path.exists(override):
        code = open(override).read()
    if os.environ.get("FAKE_BREAK"):  # only visible if the caller's environment leaks through
        code = "broken ="
    open("rev.py", "w").write(code)
    reason = "wrote rev.py"
    if os.path.exists(os.path.join(os.environ["HOME"], "fake_surrogate")):
        reason += chr(0xD800)  # a lone surrogate: json.dumps escapes it, as the real CLI may
    say(result | {{"total_cost_usd": 0.006,
                  "structured_output": {{"status": "done", "reason": reason}}}})
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
        EventType.STARTED,
        EventType.HIRED,
        EventType.SLICE_START,
        EventType.SLICE_END,
        EventType.CHECK_RESULT,
        EventType.ROUND_CLOSED,
        EventType.CHECK_RESULT,  # the verdict on the assembled product
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


def test_a_lone_surrogate_in_a_workers_reason_does_not_break_the_report(boss):
    (boss.project.parent / "fake_surrogate").write_text("")
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    assert code == EXIT_OK
    [run_dir] = boss.runs()
    (run_dir / "report.md").read_text(encoding="utf-8")  # written, and valid UTF-8
    ends = [e for e in events_of_run(boss) if e.event is EventType.SLICE_END]
    reasons = [e.data["status"]["reason"] for e in ends]
    assert "wrote rev.py\ufffd" in reasons  # kept, visibly replaced, not dropped


def test_report_and_status_read_the_latest_run(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50")
    code, report = boss("report")
    assert code == EXIT_OK and "BOARD REPORT" in report
    code, status = boss("status")
    assert code == EXIT_OK
    assert "last event gate check_result; 1/1 checks passing; spend $0.0100 estimated" in status


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


@pytest.mark.parametrize("option", ["--slice", "--reserve"])
def test_a_bad_dollar_amount_names_its_own_option_and_value_not_the_budget(boss, option, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "x", "--budget", "0.50", option, "0")
    assert info.value.code == 2
    error = capsys.readouterr().err.strip().splitlines()[-1]  # the line after the usage
    assert f"argument {option}: '0' is not a positive dollar amount" in error
    assert "budget" not in error


def test_a_budget_too_small_for_one_slice_is_refused_before_anything_is_spent(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.104999")
    assert code == EXIT_USAGE
    assert "cannot fund one worker slice" in output and "at least $0.105" in output
    assert not (boss.project / ".boss").exists()  # no run folder, no boss call, no ledger


def test_the_early_budget_check_refuses_only_what_no_round_plan_could_fund(boss):
    # The boss may draft one check, which makes one round of the whole budget: $0.30 over three
    # rounds is fundable until the draft says otherwise.
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.30", "--rounds", "3")
    assert code == EXIT_OK
    [closed] = [e for e in events_of_run(boss) if e.event is EventType.ROUND_CLOSED]
    assert closed.round == 1  # the one-check draft planned one round, with all $0.30
    code, output = boss("fund", "Reverse a string.", "--budget", "0.104999", "--rounds", "3")
    assert code == EXIT_USAGE and "cannot fund one worker slice" in output
    assert len(boss.runs()) == 1  # the refusal made no run folder


@pytest.mark.parametrize(
    ("budget", "extra", "rounds"),
    [
        # Two checks over $0.20 would be two rounds of $0.10, each under the $0.105 one slice
        # needs: the plan keeps one round instead of paying for a draft that is then refused.
        ("0.20", (), [200_000]),
        ("0.21", (), [105_000, 105_000]),
        # A Sonnet worker's $0.30 reserve raises the floor to $0.305: $0.60 is one round.
        ("0.60", ("--model", "sonnet"), [600_000]),
        ("0.62", ("--model", "sonnet"), [310_000, 310_000]),
        ("0.60", ("--reserve", "0.30"), [600_000]),
    ],
)
def test_the_boss_drafts_only_rounds_the_runs_reserve_can_fund(boss, budget, extra, rounds):
    (boss.project.parent / "fake_two_checks").write_text("")
    argv = ("fund", "Reverse a string.", "--budget", budget, "--rounds", "3", *extra)
    code, output = boss(*argv, answers=("r",))
    assert code == EXIT_FAILED and "Rejected. Nothing was funded." in output  # got to approval
    [run_dir] = boss.runs()
    sheet = json.loads((run_dir / "term_sheet.json").read_text())
    assert [r["budget_micros"] for r in sheet["rounds"]] == rounds


def test_a_plan_with_a_round_below_the_minimum_is_still_refused_after_the_draft(boss, monkeypatch):
    (boss.project.parent / "fake_two_checks").write_text("")
    real = cli_module.plan_rounds
    monkeypatch.setattr(
        cli_module, "plan_rounds", lambda b, n, r, *, min_round_micros: real(b, n, r)
    )  # a planner that ignores the floor
    # No answers are given: asking the investor to approve would raise.
    argv = ("fund", "Reverse a string.", "--budget", "0.20", "--rounds", "3")
    code, output = boss(*argv, answers=())
    assert code == EXIT_FAILED and "smallest has $0.1" in output and "at least $0.105" in output
    events = read_events(boss.runs()[0] / "ledger.jsonl")
    assert [e.event for e in events] == [EventType.BOSS_CALL, EventType.STOPPED]  # paid, no hire
    assert "smallest has $0.1" in events[-1].data["reason"]


def test_reserve_option_reaches_the_slice_cap(boss):
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.05", "--reserve", "0.01")
    assert code == EXIT_OK
    [start] = [e for e in read_events(boss.runs()[0] / "ledger.jsonl") if e.event == "slice_start"]
    assert start.data["cap_micros"] == 40_000  # 0.05 budget - 0.01 reserve, under the 0.10 slice


def test_worker_thinking_reaches_every_slice_and_the_started_config(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50", "--worker-thinking", "0")
    assert (boss.project.parent / "worker_thinking.txt").read_text() == "0"
    [started] = [e for e in events_of_run(boss) if e.event is EventType.STARTED]
    assert started.data["config"]["thinking_tokens"] == 0
    boss("fund", "Reverse a string.", "--budget", "0.50")
    assert (boss.project.parent / "worker_thinking.txt").read_text() == "unset"


def started_reserve(boss, n=0):
    started = next(e for e in events_of_run(boss, n) if e.event is EventType.STARTED)
    return started.data["config"]["reserve_micros"]


@pytest.mark.parametrize(
    ("model", "micros"),
    [("haiku", 100_000), ("sonnet", 300_000), ("opus", 500_000), ("x", 100_000)],
)
def test_the_reserve_defaults_by_worker_model_and_is_recorded_on_started(boss, model, micros):
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.80", "--model", model)
    assert code == EXIT_OK
    assert started_reserve(boss) == micros


def test_an_explicit_reserve_beats_the_model_default(boss):
    argv = ("fund", "Reverse a string.", "--budget", "0.50", "--model", "opus", "--reserve", "0.02")
    code, _ = boss(*argv)
    assert code == EXIT_OK
    assert started_reserve(boss) == 20_000


def test_a_budget_below_the_model_reserve_plus_a_slice_is_refused_before_anything_is_spent(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.30", "--model", "sonnet")
    assert code == EXIT_USAGE and "at least $0.305" in output and "$0.3 reserve" in output
    assert not (boss.project / ".boss").exists()


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


def wrong_product(boss):
    (boss.project.parent / "fake_product.py").write_text("def reverse(s):\n    return s\n")


def events_of_run(boss, n=0):
    return read_events(boss.runs()[n] / "ledger.jsonl")


def test_resume_continues_a_run_that_was_stopped_and_records_who_lifted_the_stop(boss):
    # A wall-clock limit stops the run before any slice. Resuming uses the configuration the run
    # was started with, which includes that limit, so it stops again at once: nothing is
    # silently loosened by resuming.
    boss("fund", "Reverse a string.", "--budget", "0.50", "--max-minutes", "1e-9")
    code, output = boss("resume")
    assert code == EXIT_INCOMPLETE
    assert "was stopped:" in output and "wall clock" in output
    kinds = [e.event for e in events_of_run(boss)]
    assert kinds.count(EventType.RESUMED) == 1 and kinds.count(EventType.STOPPED) == 2
    resumed = next(e for e in events_of_run(boss) if e.event is EventType.RESUMED)
    assert resumed.actor == "investor"
    assert kinds.count(EventType.STARTED) == 1 and kinds.count(EventType.SLICE_START) == 0


def test_resume_finishes_an_interrupted_run_without_a_new_draft_or_a_second_hire(boss):
    (boss.project.parent / "fake_interrupt").write_text("")
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    assert code == EXIT_INTERRUPTED
    [run_dir] = boss.runs()
    assert f"continue with `boss resume {run_dir.name}`" in output
    (boss.project.parent / "fake_interrupt").unlink()
    code, output = boss("resume", run_dir.name)
    assert code == EXIT_OK and "Round 1: 1/1 checks passed" in output
    kinds = [e.event for e in events_of_run(boss)]
    assert kinds.count(EventType.BOSS_CALL) == 1 and kinds.count(EventType.HIRED) == 1
    assert kinds.count(EventType.SLICE_START) == 2 and kinds.count(EventType.SLICE_END) == 1
    assert EventType.RESUMED not in kinds  # an interruption is not a stop; nothing to lift
    assert len(boss.runs()) == 1


def test_resume_uses_the_configuration_the_run_started_with(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50", "--slice", "0.07", "--reserve", "0.03",
         "--max-minutes", "1e-9")  # fmt: skip
    started = next(e for e in events_of_run(boss) if e.event is EventType.STARTED)
    assert started.data["config"]["slice_micros"] == 70_000
    assert started.data["config"]["reserve_micros"] == 30_000
    assert started.data["config"]["limits"]["max_seconds"] == pytest.approx(6e-8)


def test_resume_refuses_a_run_whose_checks_changed_and_spends_nothing(boss):
    wrong_product(boss)
    boss("fund", "Reverse a string.", "--budget", "0.50", "--max-slices", "1")
    [run_dir] = boss.runs()
    before = len(events_of_run(boss))
    (run_dir / "checks" / "test_c01.py").write_text("def test_x():\n    pass\n")
    code, output = boss("resume")
    assert code == EXIT_FAILED
    assert "no matching investor approval" in output and "Nothing was spent" in output
    assert len(events_of_run(boss)) == before


def test_resume_without_a_run_or_before_any_hiring_says_what_to_do(boss):
    code, output = boss("resume")
    assert code == EXIT_FAILED and "No runs under" in output
    boss("fund", "Reverse a string.", "--budget", "0.50", answers=("r",))
    code, output = boss("resume")
    assert code == EXIT_FAILED and "never got as far as hiring" in output
    (boss.runs()[0] / "term_sheet.json").write_text("{not json")
    code, output = boss("resume")
    assert code == EXIT_FAILED and "no usable term sheet" in output


def test_resuming_a_finished_run_changes_nothing_and_spends_nothing(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50")
    before = events_of_run(boss)
    code, output = boss("resume")
    assert code == EXIT_OK and "Round 1: 1/1 checks passed" in output
    assert events_of_run(boss) == before


def test_resuming_a_finished_run_that_used_roles_changes_nothing_and_spends_nothing(boss):
    # This fake answers every role with the boss's draft, which no role's gate accepts: both
    # calls are booked as failed, and a resume (whose roles come from the ledger) adds nothing.
    code, output = boss(
        "fund", "Reverse a string.", "--budget", "0.50", "--roles", "check_auditor,critic"
    )
    assert (
        code == EXIT_OK
        and "The check_auditor failed (" in output
        and "The critic failed (" in output
    )
    calls = [e for e in events_of_run(boss) if e.event is EventType.ROLE_CALL]
    assert [(e.actor, e.cost_micros, e.data["result"]) for e in calls] == [
        ("role:check_auditor", 4_000, "failed"),
        ("role:critic", 4_000, "failed"),
    ]
    before = events_of_run(boss)
    for _ in range(2):
        code, output = boss("resume")
        assert code == EXIT_OK and "Roles (each call" in output
        assert events_of_run(boss) == before


def test_a_run_that_ends_early_tells_the_investor_how_to_continue(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", "--max-minutes", "1e-9")
    assert f"To continue this run: `boss resume {boss.runs()[0].name}`" in output


@pytest.mark.parametrize("option", ["--rounds", "--max-tasks", "--max-slices", "--stall-slices"])
@pytest.mark.parametrize("bad", ["0", "-1", "1.5", "two"])
def test_counts_must_be_whole_numbers_of_one_or_more(boss, option, bad, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "x", "--budget", "0.50", option, bad)
    assert info.value.code == 2
    assert "whole number of 1 or more" in capsys.readouterr().err


def test_a_slice_too_small_to_ever_be_funded_is_refused_before_anything_is_spent(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", "--slice", "0.004999")
    assert code == EXIT_USAGE and "--slice must be at least $0.005" in output
    assert not (boss.project / ".boss").exists()


@pytest.mark.parametrize("idea", ["", "   ", "\n -x", " --dangerously-skip-permissions"])
def test_a_blank_idea_or_one_that_reads_as_an_option_is_refused_before_anything_exists(boss, idea):
    # Found while documenting: this ended in a traceback and left an empty run folder.
    code, output = boss("fund", idea, "--budget", "0.50")
    assert code == EXIT_USAGE and "The idea must be some text" in output
    assert not (boss.project / ".boss").exists()


def test_an_idea_typed_as_an_option_is_stopped_by_the_argument_parser(boss, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "--dangerously-skip-permissions", "--budget", "0.50")
    assert info.value.code == 2 and not (boss.project / ".boss").exists()


def test_resume_repairs_a_ledger_whose_last_line_was_cut_off_and_says_so(boss):
    wrong_product(boss)
    boss("fund", "Reverse a string.", "--budget", "0.50", "--max-slices", "1")
    ledger = boss.runs()[0] / "ledger.jsonl"
    whole = len(read_events(ledger))
    with ledger.open("a") as fh:
        fh.write('{"actor": "boss", "event": "hir')  # a hard kill in the middle of an append
    code, output = boss("resume")
    assert "last line was cut off by a hard stop and has been removed" in output
    assert code == EXIT_INCOMPLETE
    assert len(read_events(ledger)) >= whole  # readable again, nothing else lost


def test_resume_while_another_process_writes_the_run_is_refused_and_changes_nothing(boss):
    wrong_product(boss)
    boss("fund", "Reverse a string.", "--budget", "0.50", "--max-slices", "1")
    ledger = boss.runs()[0] / "ledger.jsonl"
    with LedgerWriter(ledger):  # the other process, still running
        with ledger.open("a") as fh:  # its append cut short: a torn tail the repair would cut
            fh.write('{"actor": "boss", "event": "hir')
        before = ledger.read_bytes()
        code, output = boss("resume")
    assert code == EXIT_FAILED
    assert "still being written by another `boss` process" in output
    assert "Traceback" not in output and "cut off" not in output
    assert ledger.read_bytes() == before


def test_a_ledger_damaged_in_the_middle_is_reported_not_repaired(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50")
    ledger = boss.runs()[0] / "ledger.jsonl"
    lines = ledger.read_text().splitlines()
    lines[2] = "not json"
    ledger.write_text("\n".join(lines) + "\n")
    before = ledger.read_text()
    for command in ("resume", "report", "status"):
        code, output = boss(command)
        assert code == EXIT_FAILED and "its ledger is damaged" in output and ":3" in output
    assert ledger.read_text() == before


def locked_run(boss):
    """A run whose only round closed below its unlock threshold because its budget ran out: a
    $0.108 round funds one slice (cap $0.008, the fake spends $0.006) and then has $0.102 left,
    short of the $0.105 a slice needs."""
    wrong_product(boss)
    code, output = boss("fund", "Reverse a string.", "--budget", "0.108")
    assert code == EXIT_INCOMPLETE, output
    [closed] = [e for e in events_of_run(boss) if e.event is EventType.ROUND_CLOSED]
    assert closed.data["unlocked"] is False
    (boss.project.parent / "fake_product.py").unlink()  # a slice from here on is right


def slices_started(boss):
    return sum(e.event is EventType.SLICE_START for e in events_of_run(boss))


def test_topup_writes_one_investor_event_for_the_round_in_micros(boss):
    locked_run(boss)
    before = events_of_run(boss)
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_OK
    assert "Topped up round 1" in output and "by $0.2:" in output and "$0.308" in output
    assert "Continue with `boss resume" in output
    events = events_of_run(boss)
    assert events[:-1] == before
    assert [(e.actor, e.event, e.round, e.data) for e in events[-1:]] == [
        ("investor", EventType.TOPPED_UP, 1, {"micros": 200_000})
    ]


def test_a_locked_round_stays_locked_on_resume_until_the_investor_tops_it_up(boss):
    locked_run(boss)
    code, output = boss("resume")
    assert code == EXIT_INCOMPLETE and slices_started(boss) == 1
    assert "Ended early: round 1 closed below its unlock threshold" in output
    assert boss("topup", "--round", "1", "--amount", "0.20")[0] == EXIT_OK
    code, output = boss("resume")
    assert code == EXIT_OK and slices_started(boss) == 2
    closed = [e.data["unlocked"] for e in events_of_run(boss) if e.event is EventType.ROUND_CLOSED]
    assert closed[-1] is True and closed[0] is False
    assert EventType.RESUMED not in [e.event for e in events_of_run(boss)]  # a lock is no stop


def test_topup_too_small_for_a_slice_says_so(boss):
    locked_run(boss)
    code, output = boss("topup", "--round", "1", "--amount", "0.001")
    assert code == EXIT_OK and "cannot fund a slice yet" in output and "$0.105" in output
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert "cannot fund a slice" not in output


def test_topup_names_the_run_it_is_given_not_only_the_latest(boss):
    locked_run(boss)
    first = boss.runs()[0].name
    wrong_product(boss)
    boss("fund", "Reverse a string.", "--budget", "0.108")
    assert len(boss.runs()) == 2
    assert boss("topup", first, "--round", "1", "--amount", "0.20")[0] == EXIT_OK
    assert events_of_run(boss, 0)[-1].event is EventType.TOPPED_UP
    assert events_of_run(boss, 1)[-1].event is not EventType.TOPPED_UP


def test_topup_lands_on_the_round_it_names(boss):
    locked_run(boss)
    path = boss.runs()[0] / "term_sheet.json"
    sheet = json.loads(path.read_text())
    sheet["rounds"].append({"n": 2, "budget_micros": 300_000, "unlock_checks": 1})
    sheet["budget_micros"] += 300_000
    path.write_text(json.dumps(sheet))
    code, output = boss("topup", "--round", "2", "--amount", "0.20")
    assert code == EXIT_OK and "Topped up round 2" in output
    last = events_of_run(boss)[-1]
    assert (last.event, last.round, last.data) == (EventType.TOPPED_UP, 2, {"micros": 200_000})


def test_topup_refuses_a_round_the_run_does_not_have_and_writes_nothing(boss):
    locked_run(boss)
    before = events_of_run(boss)
    code, output = boss("topup", "--round", "2", "--amount", "0.20")
    assert code == EXIT_USAGE and "has no round 2; its rounds are 1" in output
    assert events_of_run(boss) == before


def test_topup_refuses_a_round_that_closed_unlocked(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50")
    before = events_of_run(boss)
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_USAGE and "closed with its checks unlocked" in output
    assert events_of_run(boss) == before


@pytest.mark.parametrize("amount", ["0", "-1", "abc", "0.0000001", ""])
def test_topup_refuses_an_amount_that_is_not_a_positive_dollar_figure(boss, amount):
    locked_run(boss)
    before = events_of_run(boss)
    with pytest.raises(SystemExit) as info:
        boss("topup", "--round", "1", "--amount", amount)
    assert info.value.code == 2 and events_of_run(boss) == before


@pytest.mark.parametrize("round_arg", ["0", "-1", "x", "1.5"])
def test_topup_refuses_a_round_that_is_not_a_whole_number_of_one_or_more(boss, round_arg):
    locked_run(boss)
    with pytest.raises(SystemExit) as info:
        boss("topup", "--round", round_arg, "--amount", "0.20")
    assert info.value.code == 2


@pytest.mark.parametrize("missing", ["--round", "--amount"])
def test_topup_needs_both_a_round_and_an_amount(boss, missing):
    locked_run(boss)
    args = {"--round": "1", "--amount": "0.20"}
    del args[missing]
    with pytest.raises(SystemExit) as info:
        boss("topup", *(x for pair in args.items() for x in pair))
    assert info.value.code == 2 and events_of_run(boss)[-1].event is not EventType.TOPPED_UP


def test_topup_without_a_run_says_what_to_do(boss):
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_FAILED and "No runs under" in output
    assert not (boss.project / ".boss").exists()


def test_topup_of_a_run_without_a_usable_term_sheet_writes_nothing(boss):
    locked_run(boss)
    (boss.runs()[0] / "term_sheet.json").write_text("{}")
    before = events_of_run(boss)
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_FAILED and "cannot be topped up" in output and "Traceback" not in output
    assert events_of_run(boss) == before


def test_topup_while_another_process_writes_the_run_is_refused_and_changes_nothing(boss):
    locked_run(boss)
    ledger = boss.runs()[0] / "ledger.jsonl"
    with LedgerWriter(ledger):  # the other process, still running
        with ledger.open("a") as fh:  # its append cut short: a torn tail the repair would cut
            fh.write('{"actor": "boss", "event": "hir')
        before = ledger.read_bytes()
        code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_FAILED
    assert "still being written by another `boss` process" in output and "top up" in output
    assert "Traceback" not in output and "cut off" not in output
    assert ledger.read_bytes() == before


def test_topup_repairs_a_cut_last_line_before_it_appends(boss):
    locked_run(boss)
    ledger = boss.runs()[0] / "ledger.jsonl"
    whole = len(read_events(ledger))
    with ledger.open("a") as fh:
        fh.write('{"actor": "boss", "event": "hir')
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_OK and "last line was cut off" in output
    events = read_events(ledger)  # raises if the new line was glued onto the cut one
    assert len(events) == whole + 1 and events[-1].event is EventType.TOPPED_UP


def test_topup_of_a_ledger_damaged_in_the_middle_is_reported_and_not_changed(boss):
    locked_run(boss)
    ledger = boss.runs()[0] / "ledger.jsonl"
    lines = ledger.read_text().splitlines()
    lines[2] = "not json"
    ledger.write_text("\n".join(lines) + "\n")
    before = ledger.read_text()
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_FAILED and "its ledger is damaged" in output and ":3" in output
    assert ledger.read_text() == before


def test_roles_prints_the_organisation(boss):
    code, output = boss("roles")
    assert code == EXIT_OK
    assert output.splitlines()[0].startswith("investor  ")
    assert "generalist  [profile, off by default]" in output and "skills: builder/" in output


def test_profile_option_reaches_the_workers_prompt_and_the_ledger(boss):
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.50", "--profile", "generalist")
    assert code == EXIT_OK
    hired = next(e for e in events_of_run(boss) if e.event is EventType.HIRED)
    assert hired.data["profile"] == "generalist"


def test_an_unknown_profile_is_a_usage_error(boss, capsys):
    with pytest.raises(SystemExit) as info:
        boss("fund", "x", "--budget", "0.50", "--profile", "wizard")
    assert info.value.code == 2 and "invalid choice" in capsys.readouterr().err


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    out = capsys.readouterr().out
    assert all(
        command in out for command in ("fund", "resume", "report", "status", "roles", "doctor")
    )


def test_doctor_reports_failures_with_a_nonzero_exit(boss):
    code, output = boss("doctor", BOSS_CLAUDE_BIN="/nonexistent/claude")
    assert code == EXIT_FAILED
    assert "FAIL  claude cli" in output and "fix:" in output
