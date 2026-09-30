"""Benchmark runner against a fake `claude` that plays boss and worker. No model calls."""

import json
import sys
from pathlib import Path

import pytest

from boss.bench.results import CellResult, cell_dir, load_results
from boss.bench.run import main, run_cell
from boss.bench.tasks import load_task, load_tasks, task_set_hash

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
elif argv[argv.index("--output-format") + 1] == "json":
    say(result | {{"total_cost_usd": 0.004, "structured_output": {DRAFT!r}}})
else:
    say({INIT!r})
    open("slugify.py", "w").write(open(os.path.join(home, "product.py")).read())
    say(result | {{"total_cost_usd": 0.006,
                  "structured_output": {{"status": "done", "reason": "wrote it"}}}})
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


def test_hidden_checks_and_reference_never_reach_a_prompt_or_a_workspace(bench):
    bench("single")
    bench("firm")
    prompts = json.dumps(bench.calls())
    hidden_files = sorted(TASK.hidden_dir.glob("test_*.py"))
    for path in hidden_files:
        assert path.read_text().strip() not in prompts
        assert path.name not in prompts
    assert "hidden_checks" not in prompts and "reference" not in prompts
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
