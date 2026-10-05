import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from changed_tasks import select, validate_cached

from boss.bench.tasks import TaskError, load_task, load_tasks, task_set_hash, validate_task

TASKS = Path(__file__).parent.parent / "bench" / "tasks"


@pytest.fixture
def task_dir(tmp_path):
    """A private copy of a real task that a test can break."""
    target = tmp_path / "slugify"
    shutil.copytree(TASKS / "slugify", target)
    return target


def problems(task_dir) -> list[str]:
    with pytest.raises(TaskError) as info:
        validate_task(load_task(task_dir))
    return info.value.problems


# What the benchmark arms are scored against: the idea, hidden checks and reference of all 17
# tasks. It must not move when mutants are added: results recorded under it stay comparable.
SHIPPED_SET_HASH = "0a83fc97a753b08c"  # 59 tasks since 2026-10-03
ORIGINAL_SET_HASH = "c130282a6eec5fe8"  # the first 17, which every earlier result ran on


def test_every_shipped_task_is_valid():
    tasks = load_tasks(TASKS)
    assert len(tasks) == 59, "benchmark tasks are missing"
    # Each validation is many short pytest processes; running four tasks at once keeps it quick.
    # All tasks are loaded and counted above; BOSS_VALIDATE_TASKS_SINCE (pull-request CI) narrows
    # only which of them are run through the gate.
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda t: validate_cached(t, validate_task), select(tasks)))


def test_the_shipped_task_set_hash_is_pinned():
    assert task_set_hash(load_tasks(TASKS)) == SHIPPED_SET_HASH


def test_adding_tasks_left_the_original_17_and_their_hash_untouched():
    import json

    results = TASKS.parent / "results" / "2026-09-30-final3" / "results.jsonl"
    ran = {json.loads(line)["task"] for line in results.read_text().splitlines()}
    original = [t for t in load_tasks(TASKS) if t.id in ran]
    assert len(original) == 17 and task_set_hash(original) == ORIGINAL_SET_HASH


MULTI = TASKS.parent / "tasks-multi"  # tasks of 2-3 modules, for measuring a split across workers
MULTI_SET_HASH = "ed1824911b464045"


def test_every_multi_file_task_is_valid_and_needs_more_than_one_module():
    tasks = load_tasks(MULTI)
    assert len(tasks) == 8 and task_set_hash(tasks) == MULTI_SET_HASH
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda t: validate_cached(t, validate_task), select(tasks)))
    for task in tasks:
        modules = sorted(p.name for p in task.reference_dir.glob("*.py"))
        assert len(modules) >= 2, f"{task.id} is meant to need several modules: {modules}"


def test_mutants_are_left_out_of_the_set_hash(task_dir):
    before = task_set_hash([load_task(task_dir)])
    shutil.copytree(task_dir / "mutants" / "pilot_single", task_dir / "mutants" / "one_more")
    (task_dir / "mutants" / "pilot_single" / "slugify.py").write_text("# edited\n")
    assert task_set_hash([load_task(task_dir)]) == before
    shutil.rmtree(task_dir / "mutants")
    assert task_set_hash([load_task(task_dir)]) == before


def test_too_few_hidden_checks(task_dir):
    for extra in sorted((task_dir / "hidden_checks").glob("test_*.py"))[4:]:
        extra.unlink()
    assert "needs at least 5 hidden checks, has 4" in problems(task_dir)


def test_hidden_check_that_passes_for_free_is_rejected(task_dir):
    (task_dir / "hidden_checks" / "test_free.py").write_text("def test_x():\n    assert True\n")
    assert problems(task_dir) == ["hidden check free does not fail on an empty workspace (passed)"]


def test_hidden_check_the_reference_cannot_pass_is_rejected(task_dir):
    (task_dir / "hidden_checks" / "test_impossible.py").write_text(
        "from slugify import slugify\n\ndef test_x():\n    assert slugify('a') == 'b'\n"
    )
    [problem] = problems(task_dir)
    assert problem.startswith("hidden check impossible does not pass on the reference")


def test_reference_must_be_stdlib_only(task_dir):
    source = task_dir / "reference" / "slugify.py"
    source.write_text("import requests\n" + source.read_text())
    assert "reference/slugify.py imports 'requests', which is not stdlib" in problems(task_dir)


def test_missing_reference(task_dir):
    shutil.rmtree(task_dir / "reference")
    assert "reference/ must contain the reference solution" in problems(task_dir)


def test_idea_must_not_leak_test_code(task_dir):
    idea = task_dir / "idea.md"
    idea.write_text(idea.read_text() + "\ndef test_hint():\n    pass\n")
    assert "idea.md contains test code; hidden checks must stay hidden" in problems(task_dir)


def test_id_must_match_the_folder(task_dir):
    meta = json.loads((task_dir / "meta.json").read_text())
    (task_dir / "meta.json").write_text(json.dumps(meta | {"id": "other"}))
    assert any("equal the folder name" in p for p in problems(task_dir))


@pytest.mark.parametrize(
    "meta",
    ['{"id": "slugify", "title": "t"}', '{"id": "slugify", "title": "t", "difficulty": 3}', "{"],
    ids=["missing-key", "wrong-type", "not-json"],
)
def test_malformed_meta(task_dir, meta):
    (task_dir / "meta.json").write_text(meta)
    with pytest.raises(TaskError):
        load_task(task_dir)


def test_bad_difficulty(task_dir):
    meta = json.loads((task_dir / "meta.json").read_text())
    (task_dir / "meta.json").write_text(json.dumps(meta | {"difficulty": "brutal"}))
    assert any("difficulty must be one of" in p for p in problems(task_dir))


def test_set_hash_is_stable_and_changes_with_any_file(task_dir):
    before = task_set_hash([load_task(task_dir)])
    assert before == task_set_hash([load_task(task_dir)])
    check = task_dir / "hidden_checks" / "test_basic.py"
    check.write_text(check.read_text() + "\n# edited\n")
    assert task_set_hash([load_task(task_dir)]) != before
