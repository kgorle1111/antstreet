"""bench/METHOD.md stays true: the figures, names and commands it states are the code's."""

import dataclasses
import re

import pytest
from docs_support import ROOT, captured_parser, original_tasks, read

from boss import kpi as run_kpi
from boss.bench import drafts as bench_drafts
from boss.bench import kpi as bench_kpi
from boss.bench import results, score
from boss.bench import run as bench_run
from boss.bench import table as bench_table
from boss.bench.score import DraftScore
from boss.bench.tasks import (
    MIN_MUTANTS,
    load_tasks,
    task_set_hash,
    validate_task,
)
from boss.firm import SLICE_SHARE
from boss.ledger import Event, EventType

DOC = ROOT / "bench" / "METHOD.md"


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def test_the_task_set_and_its_hash_are_the_ones_on_disk(text):
    original = original_tasks()  # the history: the first 17 and the hash re-encoding
    assert f"the same {len(original)} task files" in text
    assert "`c130282a6eec5fe8` after" in text and task_set_hash(original) == "c130282a6eec5fe8"
    tasks = load_tasks(ROOT / "bench" / "tasks")  # and the set as it is now
    assert f"the set has {len(tasks)} tasks, hash `{task_set_hash(tasks)}`" in text


def test_the_single_arms_slice_cap_is_the_share_it_states(text):
    assert f"| Slice cap | {int(SLICE_SHARE * 100)}% of the cell budget" in text
    assert bench_run.SLICE_SHARE == SLICE_SHARE


def test_the_failure_classes_named_are_the_recorded_ones(text):
    body = text.split("## Failure classes")[1].split("\n## ")[0]
    named = re.findall(r"^- \*\*(\w+)\*\*:", body, re.M)
    assert named == [c for c in results.FAILURE_CLASSES if c != "unlabelled"]
    assert "`unlabelled`" in text


def test_the_task_rules_named_are_enforced(text):
    assert "`validate_task`" in text and callable(validate_task)
    for folder in ("idea.md", "meta.json", "hidden_checks/", "reference/"):
        assert f"`{folder}`" in text
        assert any(
            (t.root / folder.strip("/")).exists() for t in load_tasks(ROOT / "bench" / "tasks")
        )


def test_the_reproducing_commands_use_real_modules_and_options(text):
    body = text.split("## Reproducing")[1]
    first, second = body.split("```bash")[1:3]
    assert "python -m boss.bench.run" in first and "python -m boss.bench.table" in first
    options = set(re.findall(r"--[a-z-]+", first))
    assert options == {"--out", "--budget", "--reps"}
    real = {s for a in captured_parser(bench_run.main)._actions for s in a.option_strings}
    assert options <= real
    assert second.count("python -m boss.bench.drafts") == 2
    drafts_options = set(re.findall(r"--[a-z-]+", second))
    assert drafts_options == {"--out", "--reps", "--prompt", "--score-existing"}
    real = {s for a in captured_parser(bench_drafts.main)._actions for s in a.option_strings}
    assert drafts_options <= real


def test_the_draft_evaluation_states_the_scores_and_layout_the_code_uses(text):
    body = text.split("## Draft evaluation")[1].split("\n## ")[0]
    assert "`bench/tasks/<id>/mutants/<name>/<module>.py`" in body
    assert f"fewer than {MIN_MUTANTS} mutants" in body
    for task in load_tasks(ROOT / "bench" / "tasks"):
        assert len(task.mutants()) >= MIN_MUTANTS
    fields = {f.name for f in dataclasses.fields(DraftScore)}
    assert {"wrong", "killed", "killed_only_by_wrong", "survived"} <= fields
    assert score.DraftScore.precision.fget and score.DraftScore.recall.fget


def test_the_firm_arm_answers_every_question_with_a(text):
    assert "every question the\n  run asks is answered `a`" in text
    assert 'ask=lambda prompt: "a"' in read(ROOT / "src" / "boss" / "bench" / "run.py")
    from boss import rulings

    for answer in ("a", "y"):  # an automatic answer is never one of the rulings
        assert (
            rulings.ask_dispute(
                lambda _, a=answer: a, task="t", worker="w", check="c", description="", reason=""
            )
            is None
        )
        assert rulings.ask_block(lambda _, a=answer: a, task="t", worker="w", reason="") is None


def test_the_interval_quoted_for_45_cells_is_about_thirteen_points(text):
    low, high = bench_table.wilson_interval(32, 45)  # 71%
    assert 0.12 <= (high - low) / 2 <= 0.14
    assert "At 70% and 45 cells that is\n  roughly ±13 points" in text


def _a_cell() -> results.CellResult:
    return results.CellResult(
        task="t",
        arm="firm",
        rep=1,
        set_hash="s",
        model="m",
        budget_micros=1,
        hidden={"a": "passed"},
        visible_passed=1,
        visible_total=1,
        cost_micros=1,
        boss_micros=0,
        unknown_cost_events=0,
        outcome="completed",
        failure_class=None,
        duration_s=1.0,
    )


def test_the_kpi_section_names_the_scorecards_seven_rows_in_order(text):
    body = text.split("## KPIs")[1].split("\n## ")[0]
    named = re.findall(r"^\d\. \*\*([^*]+)\*\*", body, re.M)
    card = bench_kpi.render_cards([("c", bench_kpi.kpi_card([_a_cell()]))])
    rows = re.findall(r"^\| (\d) ([^|]+?) +\|", card, re.M)
    assert len(named) == len(rows) == 7
    # the scorecard's row names are shorter than the note's: each row's first word opens the name
    assert [n.split()[0].lower() for n in named] == [r[1].split()[0].lower() for r in rows]
    assert "python -m boss.bench.kpi" in body and "fixed before any new run is analysed" in body


def test_the_investor_question_rule_lists_the_events_the_code_counts(text):
    rule = text.split("**Counting rule for investor questions.**")[1].split("\nNot counted")[0]
    named = set(re.findall(r"`(approved|stopped|ruled|abandoned|resumed|topped_up)`", rule))
    probes = ({"reason": "term sheet rejected"}, {"reason": "disputed"}, {})
    counted = {
        t.value
        for t in EventType
        for actor in ("investor", "boss")
        for data in probes
        if run_kpi._is_question(Event(run="r", round=0, actor=actor, event=t, data=data))
    }
    assert named == counted
    for reason in ("term sheet rejected", *run_kpi._SET_ASIDE_AFTER_QUESTION):
        assert f"`{reason}`" in rule
