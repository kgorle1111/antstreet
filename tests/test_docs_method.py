"""bench/METHOD.md stays true: the figures, names and commands it states are the code's."""

import re

import pytest
from docs_support import ROOT, captured_parser, read

from boss.bench import results
from boss.bench import run as bench_run
from boss.bench import table as bench_table
from boss.bench.tasks import (
    load_tasks,
    task_set_hash,
    validate_task,
)
from boss.firm import SLICE_SHARE

DOC = ROOT / "bench" / "METHOD.md"


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def test_the_task_set_and_its_hash_are_the_ones_on_disk(text):
    tasks = load_tasks(ROOT / "bench" / "tasks")
    assert f"the same {len(tasks)} task files" in text
    assert "`c130282a6eec5fe8` after" in text and task_set_hash(tasks) == "c130282a6eec5fe8"


def test_the_single_arms_slice_cap_is_the_share_it_states(text):
    assert f"| Slice cap | {int(SLICE_SHARE * 100)}% of the cell budget" in text
    assert bench_run.SLICE_SHARE == SLICE_SHARE


def test_the_failure_classes_named_are_the_recorded_ones(text):
    named = re.findall(r"^- \*\*(\w+)\*\*:", text, re.M)
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
    assert "python -m boss.bench.run" in body and "python -m boss.bench.table" in body
    options = set(re.findall(r"--[a-z-]+", body))
    assert options == {"--out", "--budget", "--reps"}
    real = {s for a in captured_parser(bench_run.main)._actions for s in a.option_strings}
    assert options <= real


def test_the_interval_quoted_for_45_cells_is_about_thirteen_points(text):
    low, high = bench_table.wilson_interval(32, 45)  # 71%
    assert 0.12 <= (high - low) / 2 <= 0.14
    assert "At 70% and 45 cells that is\n  roughly ±13 points" in text
