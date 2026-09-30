"""Draft evaluation against a fake `claude` that plays the boss. No model calls, no spend."""

import json
import sys
from pathlib import Path

import pytest

from boss.bench import drafts
from boss.bench.drafts import (
    FAILED,
    INVALID,
    SCORED,
    DraftCell,
    main,
    render_table,
    run_draft,
    settings_for,
    summarize,
)
from boss.bench.results import CellResult, cell_dir
from boss.bench.score import DraftScore
from boss.bench.tasks import BenchTask, load_task, load_tasks, task_set_hash
from boss.boss import load_prompt

REAL_TASKS = Path(__file__).parent.parent / "bench" / "tasks"

REFERENCE = "# REFERENCE-MARKER\ndef f(x):\n    return x + 1\n"
MUTANTS = {
    "off_by_one": "def f(x):\n    return x\n",  # fails SOUND
    "only_two": "def f(x):\n    return x + 1 if x == 1 else 0\n",  # passes SOUND, fails WRONG
}
SOUND = "from demo import f\n\ndef test_one():\n    assert f(1) == 2\n"
WRONG = "from demo import f\n\ndef test_two():\n    assert f(2) == 100\n"
PASSES_ON_NOTHING = "def test_free():\n    assert True\n"


def draft_of(*codes: str) -> dict:
    return {
        "tasks": [{"id": "t1", "brief": "Create demo.py.", "paths": ["demo.py"]}],
        "checks": [
            {"description": f"check {n}", "task": "t1", "code": c} for n, c in enumerate(codes)
        ],
    }


RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "session_id": "s-1",
    "total_cost_usd": 0.004,
    "modelUsage": {"m": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 3}},
}
FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, sys
home = os.environ["HOME"]
with open(os.path.join(home, "calls.log"), "a") as log:
    log.write(json.dumps({{"argv": sys.argv[1:], "env": sorted(os.environ)}}) + "\\n")
    log.write(json.dumps({{"thinking": os.environ.get("MAX_THINKING_TOKENS")}}) + "\\n")
mode = open(os.path.join(home, "mode")).read().strip() if os.path.exists(home + "/mode") else "ok"
base = {RESULT!r}
if mode == "login":
    print(json.dumps(base | {{"is_error": True, "api_error_status": 401,
                             "terminal_reason": "api_error", "total_cost_usd": 0,
                             "modelUsage": {{}}}}))
elif mode == "capped":
    print(json.dumps(base | {{"subtype": "error_max_budget_usd", "is_error": True,
                             "terminal_reason": "budget_exhausted", "total_cost_usd": 0.25}}))
elif mode == "crash":
    pass
elif mode == "empty":
    print(json.dumps(base))
else:
    drafts = json.load(open(os.path.join(home, "drafts.json")))
    idea = sys.argv[-1]
    draft = next(d for key, d in drafts.items() if key in idea)
    print(json.dumps(base | {{"structured_output": draft}}))
"""


def make_task(root: Path, name: str, mutants: dict[str, str] = MUTANTS) -> Path:
    folder = root / name
    (folder / "reference").mkdir(parents=True)
    (folder / "reference" / "demo.py").write_text(REFERENCE)
    for mutant, source in mutants.items():
        (folder / "mutants" / mutant).mkdir(parents=True)
        (folder / "mutants" / mutant / "demo.py").write_text("# MUTANT-MARKER\n" + source)
    (folder / "hidden_checks").mkdir()
    (folder / "meta.json").write_text(json.dumps({"id": name, "title": name, "difficulty": "easy"}))
    (folder / "idea.md").write_text(f"Create demo.py, marker-{name}, with f(x) returning x + 1.")
    return folder


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Two tiny tasks, a fake boss, and validation stubbed (it has its own tests)."""
    tasks = tmp_path / "tasks"
    for name in ("alpha", "beta"):
        make_task(tasks, name)
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    validated = []
    monkeypatch.setattr(drafts, "validate_task", lambda task: validated.append(task.id))

    class Env:
        pass

    e = Env()
    e.home, e.tasks, e.out, e.validated = tmp_path, tasks, tmp_path / "out", validated
    e.environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
    e.set_drafts = lambda **by_marker: (tmp_path / "drafts.json").write_text(json.dumps(by_marker))
    e.set_mode = lambda mode: (tmp_path / "mode").write_text(mode)
    e.calls = lambda: [
        c for c in map(json.loads, (tmp_path / "calls.log").read_text().splitlines()) if "argv" in c
    ]
    e.thinking = lambda: [
        c["thinking"]
        for c in map(json.loads, (tmp_path / "calls.log").read_text().splitlines())
        if "thinking" in c
    ]
    e.set_drafts(**{"marker-alpha": draft_of(SOUND, WRONG), "marker-beta": draft_of(SOUND)})
    e.settings = settings_for("term_sheet_v1.md", "haiku", None)
    e.task = lambda name: load_task(tasks / name)
    e.run = lambda argv: main(
        ["--tasks", str(tasks), "--out", str(e.out), *argv], environ=e.environ
    )
    return e


def cell(env, name="alpha", rep=1, settings=None) -> DraftCell:
    return run_draft(
        env.task(name),
        rep,
        env.out,
        environ=env.environ,
        set_hash="hash1",
        settings=settings or env.settings,
    )


# --- one draft ----------------------------------------------------------------------------------


def test_a_draft_is_saved_with_its_checks_cost_tokens_and_real_score(env):
    result = cell(env)
    assert result.status == SCORED and result.outcome == "completed" and result.detail == ""
    assert (result.cost_micros, result.tokens_in, result.tokens_out, result.tokens_cached) == (
        4_000,
        10,
        5,
        3,
    )
    assert result.score == DraftScore(
        checks=2,
        wrong=("c02",),
        mutants=2,
        killed=("off_by_one",),
        killed_only_by_wrong=("only_two",),
        survived=(),
    )
    folder = env.out / "alpha" / "rep1"
    assert (folder / "checks" / "test_c01.py").read_text() == SOUND
    assert (folder / "checks" / "test_c02.py").read_text() == WRONG
    assert DraftCell.load(folder / "draft.json") == result


def test_the_boss_sees_the_idea_with_the_chosen_prompt_model_and_thinking_and_nothing_else(env):
    settings = settings_for("solo_v1.md", "sonnet", 0)
    env.environ["SECRET_TOKEN"] = "hunter2"
    cell(env, settings=settings)
    [call] = env.calls()
    argv = call["argv"]
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--system-prompt") + 1] == load_prompt("solo_v1.md")
    assert env.task("alpha").idea in argv[-1]
    assert "SECRET_TOKEN" not in call["env"]
    assert env.thinking() == ["0"]
    cell(env, name="beta")
    assert env.thinking()[-1] is None


def test_hidden_checks_reference_and_mutants_never_reach_the_boss(env):
    (env.tasks / "alpha" / "hidden_checks" / "test_secret.py").write_text("# HIDDEN-MARKER\n")
    cell(env)
    calls = json.dumps(env.calls())
    for word in ("HIDDEN-MARKER", "MUTANT-MARKER", "REFERENCE-MARKER", "off_by_one", "only_two"):
        assert word not in calls


def test_a_finished_draft_is_not_made_again(env):
    first = cell(env)
    env.set_mode("login")
    assert cell(env) == first
    assert len(env.calls()) == 1


def test_a_run_that_died_before_saving_starts_over_cleanly(env):
    stale = env.out / "alpha" / "rep1" / "checks"
    stale.mkdir(parents=True)
    (stale / "test_c09.py").write_text(SOUND)
    result = cell(env)
    assert result.score.checks == 2
    assert sorted(p.name for p in stale.iterdir()) == ["test_c01.py", "test_c02.py"]


@pytest.mark.parametrize(
    ("mode", "status", "outcome", "cost"),
    [
        ("login", FAILED, "login", 0),
        ("capped", FAILED, "capped", 250_000),
        ("crash", FAILED, "crashed", None),
        ("empty", INVALID, "completed", 4_000),
    ],
)
def test_a_draft_that_is_not_usable_is_recorded_as_such_with_its_cost(
    env, mode, status, outcome, cost
):
    env.set_mode(mode)
    result = cell(env)
    assert (result.status, result.outcome, result.cost_micros) == (status, outcome, cost)
    assert result.score is None and result.detail
    assert DraftCell.load(env.out / "alpha" / "rep1" / "draft.json") == result


def test_a_draft_that_fails_validation_is_invalid_and_keeps_its_checks(env):
    env.set_drafts(**{"marker-alpha": draft_of(SOUND, PASSES_ON_NOTHING)})
    result = cell(env)
    assert result.status == INVALID and result.outcome == "completed"
    assert "passes on an empty workspace" in result.detail
    assert result.cost_micros == 4_000 and result.score is None
    assert (env.out / "alpha" / "rep1" / "checks" / "test_c02.py").is_file()


# --- the command line ---------------------------------------------------------------------------


@pytest.fixture
def stub_score(monkeypatch):
    """Scoring has its own tests; here every draft kills one of two mutants and is sound."""

    def fake(task, checks_dir):
        n = len(drafts.draft_checks(checks_dir))
        return DraftScore(n, (), 2, ("off_by_one",), (), ("only_two",))

    monkeypatch.setattr(drafts, "score_draft", fake)


def test_dry_run_lists_the_drafts_and_spends_nothing(env, capsys):
    assert env.run(["--reps", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert f"task set {task_set_hash(load_tasks(env.tasks))}: 4 drafts, 4 to make" in out
    assert "up to $1 at the per-draft cap" in out
    assert "alpha rep2 (to do)" in out and "beta rep1 (to do)" in out
    assert not env.out.exists() and not (env.home / "calls.log").exists()
    assert env.validated == []


def test_the_command_line_makes_scores_and_tabulates_every_draft(env, stub_score, capsys):
    assert env.run(["--reps", "2", "--boss-model", "sonnet", "--boss-thinking", "0"]) == 0
    out = capsys.readouterr().out
    assert len(env.calls()) == 4
    assert sorted(set(env.validated)) == ["alpha", "beta"] and len(env.validated) == 2
    assert "Prompt: term_sheet_v1.md" in out and "Boss model: sonnet" in out
    assert "Thinking tokens: 0" in out
    assert "| 4 | 0 | 0 | 1.5 | $0.0040 | 0 |" in out
    assert "- wrong checks: 0 of 6 failed on the reference (precision 100%)" in out
    assert "- mutants killed by sound checks: 4 of 8 (recall 50%)" in out
    assert sorted(p.parent.name for p in env.out.glob("*/rep*/draft.json")) == [
        "rep1",
        "rep1",
        "rep2",
        "rep2",
    ]


def test_a_second_run_makes_no_calls_and_prints_the_same_table(env, stub_score, capsys):
    env.run(["--reps", "2"])
    first = capsys.readouterr().out.split("\n\n", 1)[1]
    calls, validated = len(env.calls()), len(env.validated)
    assert env.run(["--reps", "2"]) == 0
    second = capsys.readouterr().out
    assert len(env.calls()) == calls and len(env.validated) == validated
    assert "4 drafts, 0 to make" in second
    assert second.split("\n\n", 1)[1] == first


def test_more_reps_add_only_the_new_drafts_and_validate_only_what_it_runs(env, stub_score):
    env.run([])
    env.validated.clear()
    env.run(["--reps", "2", "--only", "beta"])
    assert len(env.calls()) == 3
    assert env.validated == ["beta"]


def test_drafts_made_with_other_settings_are_refused_before_anything_is_spent(
    env, stub_score, capsys
):
    env.run([])
    calls = len(env.calls())
    capsys.readouterr()
    for extra in (
        ["--boss-model", "opus"],
        ["--boss-thinking", "1000"],
        ["--prompt", "solo_v1.md"],
    ):
        assert env.run(extra) == 1
        err = capsys.readouterr().err
        assert "draft.json was drafted with" in err and "fresh --out" in err
    assert len(env.calls()) == calls


def test_a_prompt_edited_in_place_counts_as_another_prompt(env, stub_score, monkeypatch, capsys):
    env.run([])
    real = drafts.load_prompt
    monkeypatch.setattr(drafts, "load_prompt", lambda name: real(name) + "\nA new rule.\n")
    assert env.run([]) == 1
    assert "fresh --out" in capsys.readouterr().err


def test_failed_and_invalid_drafts_are_excluded_from_every_rate_but_reported(
    env, stub_score, capsys
):
    env.set_drafts(
        **{"marker-alpha": draft_of(SOUND, PASSES_ON_NOTHING), "marker-beta": draft_of(SOUND)}
    )
    assert env.run([]) == 0
    out = capsys.readouterr().out
    assert "| 1 | 1 | 0 | 1.0 | $0.0040 | 0 |" in out
    assert "alpha" in out and "invalid (completed)" in out
    env.set_mode("login")
    assert env.run(["--reps", "2"]) == 0
    assert "| 1 | 1 | 2 | 1.0 |" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--only", "nope"], "no matching tasks"),
        (["--prompt", "no_such_prompt.md"], "cannot use prompt 'no_such_prompt.md'"),
        (["--prompt", "../x.md"], "cannot use prompt"),
    ],
)
def test_bad_selections_fail_before_any_call(env, capsys, argv, message):
    assert env.run(argv) == 1
    assert message in capsys.readouterr().err
    assert not (env.home / "calls.log").exists()


def test_arguments_are_checked(env, capsys):
    with pytest.raises(SystemExit) as info:
        main(["--tasks", str(env.tasks)], environ=env.environ)
    assert info.value.code == 2 and "--out is required" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        env.run(["--reps", "0"])
    with pytest.raises(SystemExit):
        env.run(["--boss-thinking", "lots"])


def test_a_damaged_draft_file_is_named_before_anything_is_spent(env, stub_score, capsys):
    env.run([])
    calls = len(env.calls())
    capsys.readouterr()
    (env.out / "alpha" / "rep1" / "draft.json").write_text("{")
    assert env.run(["--reps", "2"]) == 1
    assert "draft.json: not valid JSON" in capsys.readouterr().err
    assert len(env.calls()) == calls


def test_the_real_task_set_is_listed_under_its_pinned_hash(capsys):
    assert main(["--tasks", str(REAL_TASKS), "--out", "/nonexistent/unused", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "task set c130282a6eec5fe8: 17 drafts, 17 to make" in out


def test_tasks_are_validated_before_the_first_paid_call(env, monkeypatch):
    def refuse(task):
        raise RuntimeError("task is broken")

    monkeypatch.setattr(drafts, "validate_task", refuse)
    with pytest.raises(RuntimeError):
        env.run([])
    assert not (env.home / "calls.log").exists()


# --- the table by hand --------------------------------------------------------------------------


def draft_cell(task, rep, status, score, cost, **changes) -> DraftCell:
    fields = {
        "task": task,
        "rep": rep,
        "set_hash": "h",
        "prompt": "p.md",
        "prompt_sha": "abc",
        "boss_model": "haiku",
        "boss_thinking": None,
        "status": status,
        "outcome": "completed" if status != FAILED else "login",
        "detail": "" if status == SCORED else "why",
        "cost_micros": cost,
        "tokens_in": 1,
        "tokens_out": 2,
        "tokens_cached": 0,
        "score": score,
    }
    return DraftCell(**(fields | changes))


WORKED = [
    # 4 checks, one wrong; 3 of 4 mutants killed, the fourth only by the wrong check
    draft_cell("a", 1, SCORED, DraftScore(4, ("c03",), 4, ("m1", "m2", "m3"), ("m4",), ()), 10_000),
    # 6 sound checks that kill all four mutants
    draft_cell("a", 2, SCORED, DraftScore(6, (), 4, ("m1", "m2", "m3", "m4"), (), ()), 20_000),
    draft_cell("b", 1, INVALID, None, 30_000),
    draft_cell("b", 2, FAILED, None, None),
    # 2 wrong checks; all three mutants fail only those
    draft_cell("b", 3, SCORED, DraftScore(2, ("c01", "c02"), 3, (), ("m1", "m2", "m3"), ()), 0),
]


def test_summary_of_a_hand_worked_set_of_drafts():
    s = summarize(WORKED)
    assert (s.calls, s.drafts, s.invalid, s.failed) == (5, 3, 1, 1)
    assert (s.checks, s.wrong_checks, s.wrong_drafts) == (12, 3, 2)
    assert s.precision == 9 / 12
    assert (s.mutants, s.killed, s.killed_only_by_wrong, s.perfect_drafts) == (11, 7, 4, 1)
    assert s.recall == 7 / 11
    assert s.mean_cost_micros == 15_000  # (10k + 20k + 30k + 0) / 4 calls of known cost
    assert s.unknown_cost_calls == 1


def test_the_table_of_a_hand_worked_set_of_drafts():
    table = render_table(WORKED)
    assert "Task set: h | Prompt: p.md | Boss model: haiku | Thinking tokens: default" in table
    assert "WARNING" not in table
    assert "| 3 | 1 | 1 | 4.0 | $0.0150 | 1 |" in table
    assert "- wrong checks: 3 of 12 failed on the reference (precision 75%)" in table
    assert "- drafts with a wrong check: 2/3 = 67% [21-94%]" in table
    assert "- mutants killed by sound checks: 7 of 11 (recall 64%)" in table
    assert "- mutants failing only wrong checks, not counted: 4" in table
    assert "- drafts that kill every mutant: 1/3 = 33% [6-79%]" in table
    assert "| a | 2 | 1/10 | 7/8 | 1/2 | 0 |" in table
    assert "| b | 1 | 2/2 | 0/3 | 0/1 | 2 |" in table
    assert "excluded from every rate" in table


def test_a_table_without_scored_drafts_has_no_rates():
    table = render_table([draft_cell("a", 1, FAILED, None, None)])
    assert "| 0 | 0 | 1 | n/a | n/a | 1 |" in table
    assert "Precision" not in table and "Recall" not in table


def test_mixed_settings_are_flagged():
    mixed = [*WORKED[:1], draft_cell("a", 2, SCORED, WORKED[1].score, 0, boss_model="sonnet")]
    assert "WARNING: results mix" in render_table(mixed)
    assert "Boss model: haiku, sonnet" in render_table(mixed)


def test_an_empty_set_cannot_be_tabulated():
    with pytest.raises(ValueError, match="empty"):
        render_table([])


# --- the saved file -----------------------------------------------------------------------------


def test_a_draft_needs_a_score_exactly_when_it_is_scored():
    with pytest.raises(ValueError, match="score exactly when"):
        draft_cell("a", 1, SCORED, None, 0)
    with pytest.raises(ValueError, match="score exactly when"):
        draft_cell("a", 1, INVALID, WORKED[1].score, 0)
    with pytest.raises(ValueError, match="status must be one of"):
        draft_cell("a", 1, "great", None, 0)


@pytest.mark.parametrize(
    "change",
    [
        {"rep": "1"},
        {"rep": True},
        {"cost_micros": 1.5},
        {"boss_thinking": "0"},
        {"score": []},
        {"score": {"checks": 1}},
        "extra",
        "missing",
    ],
    ids=[
        "str-rep",
        "bool-rep",
        "float-cost",
        "str-thinking",
        "list-score",
        "short-score",
        "extra",
        "missing",
    ],
)
def test_a_damaged_saved_draft_is_refused_naming_the_file(tmp_path, change):
    WORKED[0].save(tmp_path)
    path = tmp_path / "draft.json"
    raw = json.loads(path.read_text())
    if change == "extra":
        raw["x"] = 1
    elif change == "missing":
        del raw["outcome"]
    else:
        raw.update(change)
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="draft.json"):
        DraftCell.load(path)


def test_a_saved_draft_survives_a_round_trip_including_unknown_cost(tmp_path):
    for original in (WORKED[0], WORKED[3]):
        original.save(tmp_path)
        assert DraftCell.load(tmp_path / "draft.json") == original


# --- scoring what boss.bench.run already saved ----------------------------------------------------


def save_firm_cell(results: Path, task: str, rep: int, checks: dict[str, str] | None, arm="firm"):
    result = CellResult(
        task=task,
        arm=arm,
        rep=rep,
        set_hash="oldhash",
        model="haiku",
        budget_micros=400_000,
        hidden={"x": "failed"},
        visible_passed=None,
        visible_total=None,
        cost_micros=9_000,
        boss_micros=7_000,
        unknown_cost_events=0,
        outcome="completed",
        failure_class="unlabelled",
        duration_s=1.0,
    )
    folder = cell_dir(results, task, arm, rep)
    result.save(folder)
    for name, code in (checks or {}).items():
        target = folder / ".boss" / "runs" / "run-1" / "checks" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code)


def test_existing_drafts_are_scored_for_free_and_cells_without_a_draft_are_counted(env, capsys):
    results = env.home / "results"
    save_firm_cell(results, "alpha", 1, {"test_c01.py": SOUND, "test_c02.py": WRONG})
    save_firm_cell(results, "beta", 1, {"test_c01.py": SOUND})
    save_firm_cell(results, "beta", 2, None)  # the boss never produced a draft
    save_firm_cell(results, "beta", 3, {})  # an empty checks folder is no draft either
    save_firm_cell(results, "alpha", 2, {"test_c01.py": SOUND}, arm="single")  # not a firm cell
    save_firm_cell(results, "gamma", 1, {"test_c01.py": SOUND})  # a task that is not in --tasks
    argv = ["--tasks", str(env.tasks), "--score-existing", str(results)]
    assert main(argv, environ={"BOSS_CLAUDE_BIN": "/nonexistent/claude"}) == 0
    out = capsys.readouterr().out
    assert "Task set: oldhash | Prompt: as run" in out
    assert "| 2 | 0 | 0 | 1.5 | $0.0070 | 0 |" in out
    assert "- wrong checks: 1 of 3 failed on the reference (precision 67%)" in out
    assert "- mutants killed by sound checks: 2 of 4 (recall 50%)" in out
    assert "- mutants failing only wrong checks, not counted: 1" in out
    assert "| alpha | 1 | 1/2 | 1/2 | 0/1 | 0 |" in out
    assert "| beta | 1 | 0/1 | 1/2 | 0/1 | 0 |" in out
    assert "gamma" not in out
    assert "Firm cells with no draft to score: 2." in out
    assert not (env.home / "calls.log").exists()
    assert env.validated == []
    assert not env.out.exists()


def test_scoring_existing_drafts_reports_a_damaged_or_empty_results_folder(env, capsys):
    argv = ["--tasks", str(env.tasks), "--score-existing"]
    assert main([*argv, str(env.home / "nothing")], environ=env.environ) == 1
    assert "no boss drafts found" in capsys.readouterr().err
    results = env.home / "results"
    save_firm_cell(results, "alpha", 1, {"test_c01.py": SOUND})
    (cell_dir(results, "alpha", "firm", 1) / "result.json").write_text("{")
    assert main([*argv, str(results)], environ=env.environ) == 1
    assert "cannot read results" in capsys.readouterr().err


def test_a_task_that_is_not_a_bench_task_is_ignored_when_scoring_existing(env):
    results = env.home / "results"
    save_firm_cell(results, "alpha", 1, {"test_c01.py": SOUND})
    cells, without = drafts.existing_drafts(
        results, [BenchTask("alpha", "a", "easy", env.tasks / "alpha")]
    )
    assert [c.task for c in cells] == ["alpha"] and without == 0
