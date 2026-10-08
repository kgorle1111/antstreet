"""CI skips revalidating a benchmark task that passed under the same files and validator."""

import shutil
from pathlib import Path

import pytest
from changed_tasks import CACHE_ENV, VALIDATOR_FILES, validate_cached, validation_key

from antstreet.bench.tasks import BenchTask

REAL = Path(__file__).resolve().parent.parent


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A fake repo root holding the validator files, one task folder, and an empty cache."""
    root = tmp_path / "repo"
    for name in VALIDATOR_FILES:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(f"# {name}\n")
    task_root = root / "bench" / "tasks" / "t1"
    (task_root / "hidden_checks").mkdir(parents=True)
    (task_root / "idea.md").write_text("idea\n")
    (task_root / "hidden_checks" / "test_a.py").write_text("def test_a(): pass\n")
    monkeypatch.setenv(CACHE_ENV, str(tmp_path / "cache"))
    return root, BenchTask("t1", "T", "easy", task_root)


def run(world, calls, fail=False):
    root, task = world

    def validate(t):
        calls.append(t.id)
        if fail:
            raise RuntimeError("invalid")

    validate_cached(task, validate, root)


def test_a_passed_task_is_not_validated_again(world):
    calls: list[str] = []
    run(world, calls)
    run(world, calls)
    assert calls == ["t1"]


def test_a_changed_task_file_invalidates_the_entry(world):
    calls: list[str] = []
    run(world, calls)
    (world[1].root / "hidden_checks" / "test_a.py").write_text("def test_a(): assert 1\n")
    run(world, calls)
    assert calls == ["t1", "t1"]


def test_an_added_or_renamed_task_file_invalidates_the_entry(world):
    calls: list[str] = []
    run(world, calls)
    (world[1].root / "idea.md").rename(world[1].root / "idea2.md")
    run(world, calls)
    assert calls == ["t1", "t1"]


@pytest.mark.parametrize("name", VALIDATOR_FILES)
def test_a_changed_validator_file_invalidates_the_entry(world, name):
    calls: list[str] = []
    run(world, calls)
    (world[0] / name).write_text("# changed\n")
    run(world, calls)
    assert calls == ["t1", "t1"]


def test_a_failure_is_never_remembered(world):
    calls: list[str] = []
    with pytest.raises(RuntimeError):
        run(world, calls, fail=True)
    run(world, calls)
    assert calls == ["t1", "t1"]


def test_without_a_cache_folder_every_run_validates(world, monkeypatch):
    monkeypatch.delenv(CACHE_ENV)
    calls: list[str] = []
    run(world, calls)
    run(world, calls)
    assert calls == ["t1", "t1"]


def test_the_key_of_a_real_task_is_stable_and_names_every_validator_file(tmp_path):
    copy = tmp_path / "slugify"
    shutil.copytree(REAL / "bench" / "tasks" / "slugify", copy)
    task = BenchTask("slugify", "S", "easy", copy)
    assert validation_key(task, REAL) == validation_key(task, REAL)
    assert all((REAL / name).is_file() for name in VALIDATOR_FILES)


def test_the_workflow_cache_key_hashes_every_validator_file():
    workflow = (REAL / ".github" / "workflows" / "ci.yml").read_text()
    assert all(f"'{name}'" in workflow for name in VALIDATOR_FILES)
