import json
import shutil
from pathlib import Path

import pytest

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


def test_every_shipped_task_is_valid():
    tasks = load_tasks(TASKS)
    assert tasks, "no benchmark tasks found"
    for task in tasks:
        validate_task(task)


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
