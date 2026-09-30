"""Mutants: known-wrong solutions that every benchmark task carries, and their validation."""

import shutil
import subprocess
from pathlib import Path

import pytest

from boss.bench import tasks as bench_tasks
from boss.bench.tasks import (
    MIN_MUTANTS,
    TaskError,
    gate_problems,
    load_task,
    load_tasks,
    structural_problems,
    validate_task,
)

TASKS = Path(__file__).parent.parent / "bench" / "tasks"
REFERENCE = (TASKS / "slugify" / "reference" / "slugify.py").read_text()


@pytest.fixture
def task_dir(tmp_path):
    """A private copy of a real task, with exactly three mutants, that a test can break."""
    target = tmp_path / "slugify"
    shutil.copytree(TASKS / "slugify", target)
    for extra in sorted((target / "mutants").iterdir())[MIN_MUTANTS:]:
        shutil.rmtree(extra)
    return target


def add_mutant(task_dir: Path, name: str, source: str, file: str = "slugify.py") -> Path:
    folder = task_dir / "mutants" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / file).write_text(source)
    return folder


def structural(task_dir: Path) -> list[str]:
    return structural_problems(load_task(task_dir))


def gate(task_dir: Path) -> list[str]:
    return gate_problems(load_task(task_dir))


# --- the shipped corpus ----------------------------------------------------------------------


def all_mutant_sources():
    for task in load_tasks(TASKS):
        for mutant in task.mutants():
            for source in sorted(mutant.glob("*.py")):
                yield task, mutant, source


def test_every_shipped_task_has_at_least_three_mutants():
    for task in load_tasks(TASKS):
        assert len(task.mutants()) >= MIN_MUTANTS, task.id


def test_every_shipped_mutant_says_what_is_wrong_on_its_first_line():
    for _, mutant, source in all_mutant_sources():
        first = source.read_text().splitlines()[0]
        assert first.startswith("# ") and len(first) > 20, f"{mutant.name}/{source.name}"


def test_no_shipped_mutant_carries_a_path_or_a_name_from_the_machine_it_came_from():
    for _, mutant, source in all_mutant_sources():
        text = source.read_text()
        found = [w for w in ("/Users/", "/home/", "/private/", "/tmp/", "/var/") if w in text]
        found += [w for w in ("kannish", "claude", "anthropic") if w in text.lower()]
        assert not found, f"{mutant.name}/{source.name}: {found}"


def test_no_two_mutants_of_a_task_are_byte_identical():
    for task in load_tasks(TASKS):
        blobs = [
            tuple(sorted((p.name, p.read_bytes()) for p in m.glob("*.py"))) for m in task.mutants()
        ]
        assert len(set(blobs)) == len(blobs), task.id


# --- static rules ----------------------------------------------------------------------------


def test_a_task_needs_at_least_three_mutants(task_dir):
    shutil.rmtree(sorted((task_dir / "mutants").iterdir())[0])
    assert structural(task_dir) == [f"needs at least {MIN_MUTANTS} mutants, has 2"]
    shutil.rmtree(task_dir / "mutants")
    assert structural(task_dir) == [f"needs at least {MIN_MUTANTS} mutants, has 0"]


def test_a_mutant_must_be_standard_library_only(task_dir):
    add_mutant(task_dir, "uses_requests", "import requests\n" + REFERENCE)
    assert structural(task_dir) == [
        "mutants/uses_requests/slugify.py imports 'requests', which is not stdlib"
    ]


def test_a_mutant_may_import_its_own_sibling_modules(task_dir):
    folder = add_mutant(task_dir, "two_files", "import helper\n" + REFERENCE)
    (folder / "helper.py").write_text("X = 1\n")
    assert structural(task_dir) == []


def test_a_mutant_with_a_syntax_error_or_bad_encoding_is_named(task_dir):
    add_mutant(task_dir, "broken", "def (\n")
    folder = add_mutant(task_dir, "not_text", "")
    (folder / "slugify.py").write_bytes(b"\xff\xfe = 1\n")
    assert structural(task_dir) == [
        "mutants/broken/slugify.py has a syntax error on line 1",
        "mutants/not_text/slugify.py is not valid UTF-8",
    ]


def test_a_mutant_must_provide_every_module_the_reference_does(task_dir):
    add_mutant(task_dir, "wrong_file_name", REFERENCE, file="other.py")
    assert "mutants/wrong_file_name/ is missing slugify.py" in structural(task_dir)


@pytest.mark.parametrize("name", ["Upper", "has-dash", "x", "with space", ".hidden"])
def test_a_mutant_name_must_be_a_plain_identifier(task_dir, name):
    add_mutant(task_dir, name, REFERENCE)
    assert any(f"mutant name {name!r} must be" in p for p in structural(task_dir))


def test_only_folders_may_sit_in_the_mutants_folder(task_dir):
    (task_dir / "mutants" / "notes.txt").write_text("hi")
    assert structural(task_dir) == ["mutants/ must hold only folders, found ['notes.txt']"]


# --- what the gate says about them -----------------------------------------------------------


def test_a_mutant_that_passes_every_hidden_check_is_rejected(task_dir):
    add_mutant(task_dir, "actually_right", REFERENCE)
    for other in sorted((task_dir / "mutants").iterdir()):
        if other.name != "actually_right":
            shutil.rmtree(other)
    assert gate(task_dir) == [
        "mutant actually_right passes every hidden check, so it is not a wrong solution"
    ]
    add_mutant(task_dir, "actually_right", REFERENCE.replace("max_length < 1", "max_length < 0"))
    assert gate(task_dir) == []


def test_a_mutant_that_does_not_import_is_rejected_with_the_reason(task_dir):
    for other in sorted((task_dir / "mutants").iterdir()):
        shutil.rmtree(other)
    add_mutant(task_dir, "raises_on_import", "raise RuntimeError('boom')\n")
    add_mutant(task_dir, "exits_on_import", "raise SystemExit(3)\n")
    assert gate(task_dir) == [
        "mutant exits_on_import does not import cleanly (exit 3)",
        "mutant raises_on_import does not import cleanly (RuntimeError: boom)",
    ]


def test_a_mutant_that_hangs_on_import_is_rejected(task_dir, monkeypatch):
    for other in sorted((task_dir / "mutants").iterdir()):
        shutil.rmtree(other)
    add_mutant(task_dir, "hangs", REFERENCE)

    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(bench_tasks.subprocess, "run", hang)
    assert gate(task_dir) == ["mutant hangs does not import cleanly (import took more than 30s)"]


def test_the_import_check_cannot_see_the_callers_environment(task_dir, monkeypatch):
    monkeypatch.setenv("BOSS_SECRET", "hunter2")
    for other in sorted((task_dir / "mutants").iterdir()):
        shutil.rmtree(other)
    add_mutant(
        task_dir, "reads_env", REFERENCE + "\nimport os\nassert 'BOSS_SECRET' not in os.environ\n"
    )
    assert gate(task_dir) == [
        "mutant reads_env passes every hidden check, so it is not a wrong solution"
    ]


def test_validate_task_reports_the_mutant_problems_under_the_task_name(task_dir):
    add_mutant(task_dir, "actually_right", REFERENCE)
    with pytest.raises(TaskError) as info:
        validate_task(load_task(task_dir))
    assert str(info.value).startswith("task slugify: mutant actually_right passes every hidden")
