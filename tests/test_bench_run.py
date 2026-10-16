"""Benchmark runner against a fake `claude` that plays boss and worker. No model calls."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT

import antstreet.bench.run as run_module
from antstreet.bench.kpi import build_columns, render_cards
from antstreet.bench.results import CellResult, cell_dir, load_results
from antstreet.bench.run import main, models_used, run_cell
from antstreet.bench.table import render_table
from antstreet.bench.tasks import (
    BenchTask,
    load_task,
    load_tasks,
    task_set_digest,
    task_set_hash,
)
from antstreet.ledger import EventType, read_events
from antstreet.rundir import RunPaths

TASK = load_task(Path(__file__).parent.parent / "bench" / "tasks" / "slugify")
REFERENCE = (TASK.reference_dir / "slugify.py").read_text()
# Passes the boss's one visible check but not the hidden edge cases.
SHALLOW = "def slugify(text, max_length=None):\n    return text.lower().replace(' ', '-')\n"
VISIBLE = (
    "from slugify import slugify\n\ndef test_basic():\n"
    "    assert slugify('Hello World') == 'hello-world'\n"
)
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create slugify.py.", "paths": ["slugify.py"]}],
    "checks": [{"description": "basic", "task": "t1", "code": VISIBLE}],
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
FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, sys
home, argv = os.environ["HOME"], sys.argv[1:]
if argv == ["auth", "status"]:
    print(json.dumps({{"loggedIn": not os.path.exists(os.path.join(home, "logged_out"))}}))
    sys.exit(0)
with open(os.path.join(home, "argv.log"), "a") as log:
    log.write(json.dumps(argv) + "\\n")
with open(os.path.join(home, "env.log"), "a") as log:
    log.write(json.dumps(sorted(os.environ)) + "\\n")
say = lambda e: print(json.dumps(e), flush=True)
result = {{"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "session_id": "s-1",
          "modelUsage": {{"m": {{"inputTokens": 10, "outputTokens": 5}}}}}}
if os.path.exists(os.path.join(home, "refresh_failed")):  # CLI 2.1.292: no retry, no status
    say({{"type": "assistant", "error": "authentication_failed", "is_api_error_message": True,
         "message": {{"content": [{{"type": "text", "text": "Failed to authenticate"}}]}}}})
    say(result | {{"is_error": True, "terminal_reason": "api_error", "api_error_status": None,
                  "total_cost_usd": 0, "modelUsage": {{}}}})
elif os.path.exists(os.path.join(home, "login_broken")):
    say(result | {{"is_error": True, "api_error_status": 401, "terminal_reason": "api_error",
                  "total_cost_usd": 0, "modelUsage": {{}}}})
elif argv[argv.index("--tools") + 1] == "":
    # the boss's init names the model it was launched with, as the CLI does
    boss_ran = os.path.join(home, "boss_ran")  # what the boss's init names, when set
    named = open(boss_ran).read() if os.path.exists(boss_ran) else argv[argv.index("--model") + 1]
    say({BOSS_INIT!r} | {{"model": named}})
    draft = {DRAFT!r}
    if os.path.exists(os.path.join(home, "draft.json")):
        draft = json.load(open(os.path.join(home, "draft.json")))
    say(result | {{"total_cost_usd": 0.004, "structured_output": draft}})
else:
    ran = os.path.join(home, "ran_model")  # the model the worker's stream names, when set
    if os.path.exists(ran):
        model = open(ran).read()
        say({INIT!r} | {{"model": model}})
        say({{"type": "assistant", "message": {{"model": model, "content": []}}}})
        say({{"type": "assistant", "message": {{"model": "<synthetic>", "content": []}}}})
    else:
        say({INIT!r})
    open("slugify.py", "w").write(open(os.path.join(home, "product.py")).read())
    say(result | {{"total_cost_usd": 0.006,
                  "structured_output": {{"status": "done", "reason": "wrote it", "junk": "x"}}}})
"""


@pytest.fixture
def bench(tmp_path):
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
    results = tmp_path / "results"

    def cell(arm, product=REFERENCE, rep=1) -> CellResult:
        (tmp_path / "product.py").write_text(product)
        return run_cell(
            TASK, arm, rep, results, environ=environ, set_hash="abc123", budget_micros=400_000
        )

    cell.home = tmp_path
    cell.results = results
    cell.environ = environ
    cell.calls = lambda: [
        json.loads(line) for line in (tmp_path / "argv.log").read_text().splitlines()
    ]
    return cell


def test_single_arm_with_a_correct_product(bench):
    result = bench("single")
    assert result.passed and result.failure_class is None
    assert set(result.hidden.values()) == {"passed"} and result.hidden_total == 6
    assert (result.cost_micros, result.boss_micros) == (6_000, 0)
    assert (result.visible_passed, result.visible_total) == (None, None)
    assert result.outcome == "completed"
    assert (
        CellResult.load(cell_dir(bench.results, "slugify", "single", 1) / "result.json") == result
    )


def test_the_single_arm_records_its_final_status_word_and_the_firm_none(bench):
    single = bench("single")
    assert single.final_status == "done"
    saved = CellResult.load(cell_dir(bench.results, "slugify", "single", 1) / "result.json")
    assert saved.final_status == "done"
    assert bench("firm").final_status is None  # its claim is its checks, not a word


def test_firm_arm_with_a_correct_product(bench):
    result = bench("firm")
    assert result.passed
    assert (result.cost_micros, result.boss_micros) == (10_000, 4_000)
    assert (result.visible_passed, result.visible_total) == (1, 1)


def test_firm_can_pass_its_own_checks_and_still_fail_the_hidden_ones(bench):
    result = bench("firm", product=SHALLOW)
    assert (result.visible_passed, result.visible_total) == (1, 1)
    assert not result.passed
    assert result.hidden["basic"] == "passed" and result.hidden["accents"] == "failed"
    assert result.failure_class == "unlabelled"


# Seen in the pilot: the boss wrote this check, which the idea does not support.
WRONG = (
    "from slugify import slugify\n\ndef test_version():\n"
    "    assert slugify('Version 2.0') == 'version-20'\n"
)


def test_a_boss_check_the_reference_fails_is_counted_as_wrong(bench):
    draft = {
        "tasks": DRAFT["tasks"],
        "checks": [*DRAFT["checks"], {"description": "dots", "task": "t1", "code": WRONG}],
    }
    (bench.home / "draft.json").write_text(json.dumps(draft))
    result = bench("firm")
    assert result.wrong_checks == 1
    assert (result.visible_passed, result.visible_total) == (1, 2)
    assert result.passed  # the product is right; only the boss's check is wrong
    saved = CellResult.load(cell_dir(bench.results, "slugify", "firm", 1) / "result.json")
    assert saved.wrong_checks == 1


def test_wrong_checks_are_zero_for_a_sound_draft_and_unmeasured_without_one(bench):
    assert bench("firm").wrong_checks == 0
    assert bench("single").wrong_checks is None
    # A product that fails the boss's check says nothing about the check: the reference decides.
    broken = bench("firm", product="def slugify(text, max_length=None):\n    return 'x'\n", rep=3)
    assert (broken.visible_passed, broken.wrong_checks) == (0, 0)
    (bench.home / "login_broken").write_text("")
    assert bench("firm", rep=2).wrong_checks is None  # the boss never produced a draft


def test_hidden_checks_and_reference_never_reach_a_prompt_or_a_workspace(bench):
    bench("single")
    bench("firm")
    prompts = json.dumps(bench.calls())
    hidden_files = sorted(TASK.hidden_dir.glob("test_*.py"))
    for path in hidden_files:
        assert path.read_text().strip() not in prompts
        assert path.name not in prompts
    assert "hidden_checks" not in prompts and "reference" not in prompts
    # Mutants, the known-wrong solutions used to score boss drafts, are just as private.
    mutants = TASK.mutants()
    assert mutants
    assert "mutants" not in prompts
    for mutant in mutants:
        assert mutant.name not in prompts
        for source in mutant.glob("*.py"):
            assert source.read_text().strip() not in prompts
            assert source.read_text().splitlines()[0] not in prompts
    assert not [p for p in bench.results.rglob("*") if "mutants" in p.parts]
    workspace_files = {
        p.name
        for p in bench.results.rglob("*")
        if p.is_file() and {"workspace", "workspaces"} & set(p.parts)
    }
    assert workspace_files == {"slugify.py"}


def test_both_arms_get_the_same_idea_model_tools_and_total_budget(bench):
    bench("single")
    bench("firm")
    solo, _draft, worker = bench.calls()
    for flag in ("--model", "--tools", "--allowedTools", "--permission-mode"):
        assert solo[solo.index(flag) + 1] == worker[worker.index(flag) + 1], flag
    assert TASK.idea in solo[-1]
    # Same $0.40 cell budget: the single agent gets one slice at 80% of it; a firm worker is
    # funded in smaller slices that together can never exceed the round's budget.
    assert solo[solo.index("--max-budget-usd") + 1] == "0.32"
    assert worker[worker.index("--max-budget-usd") + 1] == "0.1"


def test_firm_options_are_passed_through_and_recorded(bench):
    (bench.home / "product.py").write_text(REFERENCE)
    result = run_cell(
        TASK,
        "firm",
        1,
        bench.results,
        environ=bench.environ,
        set_hash="abc123",
        budget_micros=400_000,
        firm_args=["--slice", "0.05", "--no-firing"],
    )
    assert result.firm_args == "--slice 0.05 --no-firing"
    worker = bench.calls()[-1]
    assert worker[worker.index("--max-budget-usd") + 1] == "0.05"


def test_the_fix_after_stop_arm_is_passed_to_fund_recorded_and_kept_apart(bench):
    (bench.home / "product.py").write_text(REFERENCE)
    options = {"environ": bench.environ, "set_hash": "abc123", "budget_micros": 400_000}
    arm = ["--roles", "critic", "--fix-after-stop"]
    result = run_cell(TASK, "firm", 1, bench.results, firm_args=arm, **options)
    assert result.firm_args == "--roles critic --fix-after-stop"
    [run] = (cell_dir(bench.results, "slugify", "firm", 1) / ".boss" / "runs").iterdir()
    started = next(e for e in RunPaths(run).events() if e.event is EventType.STARTED)
    assert started.data["roles"]["fix_after_stop"] is True
    with pytest.raises(RuntimeError, match="run with other options"):  # E4b's arm is not E4c's
        run_cell(TASK, "firm", 1, bench.results, firm_args=["--roles", "critic"], **options)


def test_the_coverage_option_runs_the_firm_arm_with_the_gate_and_records_it(bench):
    from antstreet import spec

    first, *rest = spec.split(TASK.idea.strip()).scorable
    cited = {**DRAFT, "checks": [{**DRAFT["checks"][0], "rules": [first.id]}]}
    cited["untested"] = [{"rule": r.id, "reason": "left for the test"} for r in rest]
    (bench.home / "draft.json").write_text(json.dumps(cited))
    (bench.home / "product.py").write_text(REFERENCE)
    result = run_cell(
        TASK,
        "firm",
        1,
        bench.results,
        environ=bench.environ,
        set_hash="abc123",
        budget_micros=400_000,
        coverage=True,
    )
    assert result.firm_args == "--coverage" and result.passed
    boss_calls = [c for c in bench.calls() if c[c.index("--tools") + 1] == ""]
    assert len(boss_calls) == 2, "the draft and one redraft: every other rule was left uncited"
    assert result.boss_micros == 8_000
    [run_dir] = (cell_dir(bench.results, "slugify", "firm", 1) / ".boss" / "runs").iterdir()
    assert (run_dir / "coverage.json").is_file()


def test_a_finished_cell_is_not_run_again(bench):
    first = bench("single")
    calls = len(bench.calls())
    assert bench("single", product=SHALLOW) == first
    assert len(bench.calls()) == calls


@pytest.mark.parametrize(
    ("arm", "change"),
    [
        ("firm", {"firm_args": ["--roles", "critic"]}),
        ("firm", {"budget_micros": 300_000}),
        ("single", {"model": "sonnet"}),
        ("single-review", {"set_hash": "def456"}),
    ],
)
def test_a_saved_cell_run_with_other_options_is_refused_not_reused(bench, arm, change):
    bench(arm)
    calls = len(bench.calls())
    options = {"set_hash": "abc123", "budget_micros": 400_000, **change}
    with pytest.raises(RuntimeError, match="run with other options.*its own --out"):
        run_cell(TASK, arm, 1, bench.results, environ=bench.environ, **options)
    assert len(bench.calls()) == calls


@pytest.mark.parametrize("arm", ["single", "firm"])
def test_a_cell_cut_off_before_its_result_is_refused_not_run_on_top_of(bench, arm):
    out = cell_dir(bench.results, "slugify", arm, 1)
    (out / ".boss" / "runs" / "20261003T113026Z-618816").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="cut off before its result; move the folder aside"):
        bench(arm)
    assert not (bench.home / "argv.log").exists()  # refused before any model call
    shutil.rmtree(out)
    assert bench(arm).passed


def test_login_failure_is_an_infrastructure_failure_in_both_arms(bench):
    (bench.home / "login_broken").write_text("")
    single, firm = bench("single"), bench("firm")
    assert (single.outcome, single.failure_class) == ("login", "infrastructure")
    assert (firm.outcome, firm.failure_class) == ("boss:login", "infrastructure")
    assert firm.hidden_passed == 0 and firm.visible_total is None


def test_command_line_runs_every_cell_and_saves_results(bench, capsys):
    (bench.home / "product.py").write_text(REFERENCE)
    tasks = str(TASK.root.parent)
    argv = ["--tasks", tasks, "--out", str(bench.results), "--budget", "0.40", "--only", "slugify"]
    assert main([*argv, "--dry-run"], environ=bench.environ) == 0
    assert not bench.results.exists()
    assert main(argv, environ=bench.environ) == 0
    results = load_results(bench.results)
    assert [(r.task, r.arm, r.passed) for r in results] == [
        ("slugify", "firm", True),
        ("slugify", "single", True),
    ]
    assert results[0].set_hash == task_set_hash(load_tasks(TASK.root.parent))
    assert "2/2 cells passed every hidden check" in capsys.readouterr().out


# Set by a Claude Code session in every process it starts (CLI 2.1.292, desktop app).
SESSION_VARS = {
    "CLAUDECODE": "1",
    "CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
    "CLAUDE_CODE_SESSION_ID": "s",
    "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH": "1",
    "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/x.sock",
    "CLAUDE_AGENT_SDK_VERSION": "0",
    "CLAUDE_PID": "1",
    "CLAUDE_EFFORT": "high",
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:1",
}


def test_no_claude_process_sees_the_parent_claude_code_session(bench):
    # Run from inside Claude Code, a child that inherits these talks to the parent's session.
    bench.environ.update(SESSION_VARS)
    bench("single")
    bench("firm")
    seen = [set(json.loads(line)) for line in (bench.home / "env.log").read_text().splitlines()]
    assert len(seen) == 3  # the single worker, the boss call, the firm's worker
    for names in seen:
        assert not names & set(SESSION_VARS)


def _cli(bench, *extra):
    (bench.home / "product.py").write_text(REFERENCE)
    argv = ["--tasks", str(TASK.root.parent), "--out", str(bench.results), "--budget", "0.40"]
    return main([*argv, "--only", "slugify", *extra], environ=bench.environ)


def test_a_run_is_refused_before_any_cell_when_the_cli_is_not_logged_in(bench, capsys):
    (bench.home / "logged_out").write_text("")
    assert _cli(bench) == 1
    err = capsys.readouterr().err
    assert "refused before any cell" in err and "claude auth login" in err
    assert not (bench.home / "argv.log").exists() and not bench.results.exists()


def test_a_login_that_cannot_be_checked_is_refused_too(bench, capsys):
    bench.environ["BOSS_CLAUDE_BIN"] = str(bench.home / "missing")
    assert _cli(bench) == 1
    assert "the login could not be checked" in capsys.readouterr().err


def test_a_run_stops_after_three_cells_in_a_row_fail_the_same_infrastructure_way(bench, capsys):
    (bench.home / "refresh_failed").write_text("")
    assert _cli(bench, "--arms", "single", "--reps", "6", "--jobs", "1") == 1
    assert len(bench.calls()) == 3  # cells 4 to 6 never launched a process
    assert [r.outcome for r in load_results(bench.results)] == ["login"] * 3
    err = capsys.readouterr().err
    assert "3 cells in a row ended as login" in err and "3 cells were not started" in err
    assert "claude auth login" in err


def test_the_boss_and_workers_count_toward_the_same_streak(bench, capsys):
    (bench.home / "refresh_failed").write_text("")
    assert _cli(bench, "--reps", "3", "--jobs", "1") == 1  # firm and single cells interleave
    assert len(load_results(bench.results)) == 3


def test_unknown_task_selection_fails(bench, capsys):
    argv = ["--tasks", str(TASK.root.parent), "--out", str(bench.results), "--budget", "0.40"]
    assert main([*argv, "--only", "nope"], environ=bench.environ) == 1
    assert "no matching tasks" in capsys.readouterr().err


def test_the_single_arm_cleans_the_workers_words_like_the_firm_arm(bench):
    bench("single")
    ledger = cell_dir(bench.results, "slugify", "single", 1) / "ledger.jsonl"
    events = read_events(ledger)
    [start] = [e for e in events if e.event is EventType.SLICE_START]
    [end] = [e for e in events if e.event is EventType.SLICE_END]
    assert start.data["slice"] == 1 and len(start.data["session"]) == 36
    assert end.data["slice"] == 1
    assert end.data["status"] == {"status": "done", "reason": "wrote it"}  # only the two keys


def test_a_run_paused_for_the_plan_limit_is_an_infrastructure_outcome():
    from antstreet.bench.run import _outcome
    from antstreet.ledger import Event

    def ev(kind, actor="worker:w1", **data):
        return Event(run="r", round=1, actor=actor, event=kind, data=data)

    finished = [ev(EventType.SLICE_END, outcome="completed")]
    assert _outcome(finished) == "completed"
    paused = [*finished, ev(EventType.PAUSED, actor="boss", reason="five_hour window at 96%")]
    assert _outcome(paused) == "usage_limit"


# B71: a cell the environment cut off is excluded whatever its product scored.
def test_runner_records_infrastructure_even_when_the_product_passed(bench, monkeypatch):
    monkeypatch.setattr("antstreet.bench.run._outcome", lambda events: "usage_limit")
    result = bench("single")
    assert result.passed and result.failure_class == "infrastructure" and not result.counted


def test_runner_records_infrastructure_for_a_prefixed_outcome_that_passed(bench, monkeypatch):
    monkeypatch.setattr("antstreet.bench.run._outcome", lambda events: "boss:login")
    result = bench("firm")
    assert result.passed and result.failure_class == "infrastructure"


def test_runner_leaves_a_passing_ordinary_cell_unclassified_and_counted(bench):
    result = bench("single")
    assert result.passed and result.failure_class is None and result.counted


# --- the models a cell ran, and --expect-models (E9: an alias moved mid-run) ---

PINNED = "claude-haiku-5-5"


def _cell(bench, arm, *, ran=PINNED, expect=(), boss_model=PINNED, rep=1):
    (bench.home / "ran_model").write_text(ran)
    (bench.home / "product.py").write_text(REFERENCE)
    return run_cell(
        TASK, arm, rep, bench.results, environ=bench.environ, set_hash="abc123",
        budget_micros=400_000, model=PINNED, boss_model=boss_model, expect_models=expect,
    )  # fmt: skip


def test_each_cell_records_the_models_its_logs_and_boss_calls_name(bench):
    single = _cell(bench, "single")
    assert single.models == (PINNED,)  # init and turns; `<synthetic>` names no model
    firm = _cell(bench, "firm", ran="claude-haiku-4-5", boss_model="haiku")
    assert firm.models == ("claude-haiku-4-5", "haiku")  # the worker's stream, the boss's launch
    saved = CellResult.load(cell_dir(bench.results, "slugify", "firm", 1) / "result.json")
    assert saved == firm and firm.failure_reason is None and firm.counted


def test_a_cell_that_ran_a_model_outside_expect_models_is_infrastructure_even_if_it_passed(bench):
    result = _cell(bench, "single", ran="claude-haiku-4-5-20251001", expect=(PINNED,))
    assert result.passed and result.failure_class == "infrastructure" and not result.counted
    assert result.failure_reason == (
        "ran claude-haiku-4-5-20251001, not in --expect-models claude-haiku-5-5"
    )
    assert result.outcome == "completed"  # the worker's own outcome is kept


def test_a_firm_boss_launched_on_an_alias_is_outside_pinned_expect_models(bench):
    result = _cell(bench, "firm", boss_model="haiku", expect=(PINNED,))
    assert result.failure_class == "infrastructure" and result.failure_reason is not None
    assert "ran haiku, not in" in result.failure_reason


def test_a_cell_inside_expect_models_is_counted_as_before(bench):
    for arm in ("single", "firm"):
        result = _cell(bench, arm, expect=(PINNED, "claude-opus-5-5"))
        assert result.passed and result.failure_class is None and result.counted


def test_a_saved_cell_is_not_reused_under_expect_models_it_breaks_or_did_not_record(bench):
    _cell(bench, "single", ran="claude-haiku-4-5")
    with pytest.raises(RuntimeError, match="saved with claude-haiku-4-5, not only --expect"):
        _cell(bench, "single", expect=(PINNED,))
    path = cell_dir(bench.results, "slugify", "single", 1) / "result.json"
    raw = json.loads(path.read_text())
    del raw["models"], raw["failure_reason"]  # a result written before the fields existed
    path.write_text(json.dumps(raw))
    old = CellResult.load(path)
    assert old.models is None and old.failure_reason is None
    with pytest.raises(RuntimeError, match="no record of its models"):
        _cell(bench, "single", expect=(PINNED,))
    assert _cell(bench, "single") == old  # without the option the saved cell stands


def test_a_result_whose_models_are_not_a_list_of_ids_is_refused(bench):
    _cell(bench, "single")
    path = cell_dir(bench.results, "slugify", "single", 1) / "result.json"
    raw = json.loads(path.read_text())
    for bad in ("claude-haiku-5-5", [1], {"a": "b"}):
        path.write_text(json.dumps(raw | {"models": bad}))
        with pytest.raises(ValueError, match="models"):
            CellResult.load(path)


def test_the_command_checks_expect_models_says_why_and_stops_on_a_streak(bench, capsys):
    (bench.home / "ran_model").write_text("claude-haiku-4-5")
    code = _cli(bench, "--arms", "single", "--reps", "4", "--jobs", "1",
                "--expect-models", f"{PINNED}, claude-opus-5-5")  # fmt: skip
    assert code == 1
    captured = capsys.readouterr()
    assert "infrastructure: ran claude-haiku-4-5, not in --expect-models " in captured.out
    assert "3 cells in a row ended as unexpected_model" in captured.err
    assert "an alias may have moved" in captured.err
    assert [r.failure_class for r in load_results(bench.results)] == ["infrastructure"] * 3


def test_an_empty_expect_models_id_is_a_usage_error(bench, capsys):
    with pytest.raises(SystemExit) as info:
        _cli(bench, "--expect-models", "claude-haiku-5-5,,x")
    assert info.value.code == 2
    assert "is not a comma-separated list of model ids" in capsys.readouterr().err


def test_the_table_and_the_kpi_card_show_the_model_ids_each_arm_ran(bench):
    _cell(bench, "single")
    _cell(bench, "firm", ran="claude-sonnet-5-5")
    results = load_results(bench.results)
    header = render_table(results).splitlines()[0]
    assert header.endswith(
        "| Models run: single claude-haiku-5-5; firm claude-haiku-5-5, claude-sonnet-5-5"
    )
    rows = render_cards(build_columns([bench.results])).splitlines()
    [row] = [line for line in rows if "models run" in line]
    assert "| claude-haiku-5-5, claude-sonnet-5-5 |" in row and "| claude-haiku-5-5 |" in row


def test_models_are_read_from_init_and_every_assistant_turn_of_every_worker_log(tmp_path):
    run_logs = tmp_path / ".boss" / "runs" / "r1" / "logs"
    run_logs.mkdir(parents=True)
    lines = [
        {"type": "system", "subtype": "init", "model": "claude-haiku-4-5-20251001"},
        {"type": "assistant", "message": {"model": "claude-haiku-5-5"}},  # moved mid-session
        {"type": "assistant", "message": {"model": "<synthetic>"}},
        {"type": "result", "modelUsage": {"claude-opus-5-5": {}}},  # not a turn: not read
        {"type": "system", "subtype": "thinking_tokens", "model": "ignored"},
    ]
    text = "\n".join(json.dumps(x) for x in lines) + "\nnot json\n[1]\n"
    (run_logs / "w1.jsonl").write_text(text)
    (run_logs / "w1-s1.prompt.txt").write_text('{"type": "assistant"}')  # not a stream log
    assert models_used(tmp_path, []) == ("claude-haiku-4-5-20251001", "claude-haiku-5-5")


def test_a_cell_whose_logs_name_no_model_is_not_counted_under_expect_models(bench):
    (bench.home / "product.py").write_text(REFERENCE)
    (bench.home / "ran_model").unlink(missing_ok=True)  # the fake worker then names no model
    result = run_cell(
        TASK, "single", 1, bench.results, environ=bench.environ, set_hash="abc123",
        budget_micros=400_000, model=PINNED, boss_model=PINNED, expect_models=(PINNED,),
    )  # fmt: skip
    assert result.models == () and result.passed and not result.counted
    assert result.failure_class == "infrastructure"
    assert (
        result.failure_reason
        == "no model id recorded, so --expect-models claude-haiku-5-5 is unchecked"
    )


def test_a_saved_cell_with_an_empty_model_record_is_not_reused_under_expect_models(bench):
    _cell(bench, "single")
    path = cell_dir(bench.results, "slugify", "single", 1) / "result.json"
    raw = json.loads(path.read_text())
    raw["models"] = []
    path.write_text(json.dumps(raw))
    with pytest.raises(RuntimeError, match="no record of its models"):
        _cell(bench, "single", expect=(PINNED,))


def test_the_table_warns_when_one_family_ran_under_two_ids_in_an_arm(bench):
    _cell(bench, "firm", rep=1)
    _cell(bench, "firm", rep=2, ran="claude-haiku-4-5-20251001")  # the alias moved mid-run
    text = render_table(load_results(bench.results))
    assert "WARNING: results mix" in text


def test_the_table_does_not_warn_for_a_firm_that_stepped_up_to_another_family(bench):
    _cell(bench, "firm", rep=1)
    _cell(bench, "firm", rep=2, ran="claude-sonnet-5-5")  # a step up, not drift
    assert "WARNING: results mix" not in render_table(load_results(bench.results))


def test_a_boss_call_counts_the_model_the_cli_reported_not_the_alias_it_was_launched_with(bench):
    (bench.home / "boss_ran").write_text(PINNED)  # `haiku` resolved to the pinned id
    result = _cell(bench, "firm", boss_model="haiku", expect=(PINNED,))
    assert result.models == (PINNED,) and result.counted and result.failure_class is None


def test_a_streak_of_cells_naming_no_model_stops_with_its_own_kind_and_fix(bench, capsys):
    (bench.home / "ran_model").unlink(missing_ok=True)  # the fake worker then names no model
    code = _cli(bench, "--arms", "single", "--reps", "4", "--jobs", "1", "--expect-models", PINNED)
    assert code == 1
    err = capsys.readouterr().err
    assert "3 cells in a row ended as no_model_recorded" in err
    assert "named no model" in err and "an alias may have moved" not in err


def test_a_wrong_expect_set_digest_stops_the_run_before_any_cell(bench, capsys):
    (bench.home / "logged_out").write_text("")  # the digest is checked before the login is
    right = task_set_digest(TASK.root.parent)
    wrong = "0" * 64
    assert _cli(bench, "--expect-set-digest", wrong) == 1
    err = capsys.readouterr().err
    assert wrong in err and right in err and "task set digest" in err
    assert "claude auth login" not in err
    assert not (bench.home / "argv.log").exists() and not bench.results.exists()


def test_a_wrong_expect_set_digest_stops_a_dry_run_too(bench, capsys):
    assert _cli(bench, "--dry-run", "--expect-set-digest", "f" * 64) == 1
    captured = capsys.readouterr()
    assert "cells" not in captured.out and "f" * 64 in captured.err
    assert not bench.results.exists()


def test_the_expect_set_digest_covers_the_whole_folder_not_the_only_selection(bench, capsys):
    whole = task_set_digest(TASK.root.parent)
    assert _cli(bench, "--dry-run", "--expect-set-digest", whole) == 0
    assert "slugify firm rep1" in capsys.readouterr().out
    assert _cli(bench, "--arms", "single", "--expect-set-digest", whole.upper()) == 0
    assert [r.task for r in load_results(bench.results)] == ["slugify"]


def test_the_digest_run_loads_the_snapshot_it_hashed_not_the_live_folder(
    bench, tmp_path, monkeypatch
):
    pool = tmp_path / "pool"
    shutil.copytree(TASK.root, pool / "slugify")
    registered = task_set_digest(pool)
    real_load = run_module.load_tasks
    seen: list[tuple[Path, str]] = []

    def load_after_an_edit(folder: Path) -> list[BenchTask]:
        # the live folder changes between the digest and the load
        (pool / "slugify" / "idea.md").write_text("Build something else entirely.")
        seen.append((folder, (folder / "slugify" / "idea.md").read_text()))
        return real_load(folder)

    monkeypatch.setattr(run_module, "load_tasks", load_after_an_edit)
    argv = ["--tasks", str(pool), "--out", str(bench.results), "--budget", "0.40", "--dry-run"]
    assert main([*argv, "--expect-set-digest", registered], environ=bench.environ) == 0
    ((loaded_from, idea),) = seen
    assert loaded_from != pool and "something else" not in idea


def test_a_symlinked_tasks_folder_is_refused_before_it_is_copied(bench, tmp_path, capsys):
    link = tmp_path / "linked"
    link.symlink_to(TASK.root.parent, target_is_directory=True)
    argv = ["--tasks", str(link), "--out", str(bench.results), "--budget", "0.40", "--dry-run"]
    code = main(
        [*argv, "--expect-set-digest", task_set_digest(TASK.root.parent)], environ=bench.environ
    )
    assert code == 1 and "is a symlink" in capsys.readouterr().err


def test_a_malformed_expect_set_digest_is_a_usage_error(bench, capsys):
    for bad in ("abc", "g" * 64, "ab" * 33, "ed6fd905c106f6a6"):  # the 16-hex hash is not a digest
        with pytest.raises(SystemExit) as info:
            _cli(bench, "--expect-set-digest", bad)
        assert info.value.code == 2
        assert "64 hex characters" in capsys.readouterr().err
    assert not bench.results.exists()


def test_a_pool_with_a_stray_file_is_refused_not_hashed_around_it(bench, tmp_path, capsys):
    pool = tmp_path / "pool"
    shutil.copytree(TASK.root, pool / "slugify")
    (pool / ".DS_Store").write_bytes(b"x")
    (bench.home / "product.py").write_text(REFERENCE)
    argv = ["--tasks", str(pool), "--out", str(bench.results), "--budget", "0.40"]
    assert main([*argv, "--expect-set-digest", "0" * 64], environ=bench.environ) == 1
    assert "remove it and rerun" in capsys.readouterr().err and not bench.results.exists()
