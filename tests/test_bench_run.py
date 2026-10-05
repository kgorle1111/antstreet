"""Benchmark runner against a fake `claude` that plays boss and worker. No model calls."""

import json
import shutil
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT

from boss.bench.results import CellResult, cell_dir, load_results
from boss.bench.run import main, run_cell
from boss.bench.tasks import load_task, load_tasks, task_set_hash
from boss.ledger import EventType, read_events

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
with open(os.path.join(home, "argv.log"), "a") as log:
    log.write(json.dumps(argv) + "\\n")
say = lambda e: print(json.dumps(e), flush=True)
result = {{"type": "result", "subtype": "success", "is_error": False,
          "terminal_reason": "completed", "session_id": "s-1",
          "modelUsage": {{"m": {{"inputTokens": 10, "outputTokens": 5}}}}}}
if os.path.exists(os.path.join(home, "login_broken")):
    say(result | {{"is_error": True, "api_error_status": 401, "terminal_reason": "api_error",
                  "total_cost_usd": 0, "modelUsage": {{}}}})
elif argv[argv.index("--tools") + 1] == "":
    say({BOSS_INIT!r})
    draft = {DRAFT!r}
    if os.path.exists(os.path.join(home, "draft.json")):
        draft = json.load(open(os.path.join(home, "draft.json")))
    say(result | {{"total_cost_usd": 0.004, "structured_output": draft}})
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
    from boss.bench.run import _outcome
    from boss.ledger import Event

    def ev(kind, actor="worker:w1", **data):
        return Event(run="r", round=1, actor=actor, event=kind, data=data)

    finished = [ev(EventType.SLICE_END, outcome="completed")]
    assert _outcome(finished) == "completed"
    paused = [*finished, ev(EventType.PAUSED, actor="boss", reason="five_hour window at 96%")]
    assert _outcome(paused) == "usage_limit"


# B71: a cell the environment cut off is excluded whatever its product scored.
def test_runner_records_infrastructure_even_when_the_product_passed(bench, monkeypatch):
    monkeypatch.setattr("boss.bench.run._outcome", lambda events: "usage_limit")
    result = bench("single")
    assert result.passed and result.failure_class == "infrastructure" and not result.counted


def test_runner_records_infrastructure_for_a_prefixed_outcome_that_passed(bench, monkeypatch):
    monkeypatch.setattr("boss.bench.run._outcome", lambda events: "boss:login")
    result = bench("firm")
    assert result.passed and result.failure_class == "infrastructure"


def test_runner_leaves_a_passing_ordinary_cell_unclassified_and_counted(bench):
    result = bench("single")
    assert result.passed and result.failure_class is None and result.counted
