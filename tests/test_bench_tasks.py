import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from changed_tasks import select, validate_cached

from antstreet.bench.tasks import (
    MUTANT_TIMEOUT_S,
    TaskError,
    load_task,
    load_tasks,
    task_set_digest,
    task_set_hash,
    validate_task,
)
from antstreet.gate import CheckStatus, run_gate

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
SHIPPED_SET_HASH = "8a5e54e341cdef2a"  # 59 tasks; roman (10-13), sudokucheck (10-21) rewritten
# The first 17, which every earlier result ran on. Was c130282a6eec5fe8 until the roman strict check
# was rewritten on 2026-10-13 (bench/PREREG.md): earlier results ran on the old roman file.
ORIGINAL_SET_HASH = "42c28f8aab61d518"


def test_every_shipped_task_is_valid():
    tasks = load_tasks(TASKS)
    assert len(tasks) == 59, "benchmark tasks are missing"
    # Each validation is many short pytest processes; running four tasks at once keeps it quick.
    # All tasks are loaded and counted above; BOSS_VALIDATE_TASKS_SINCE (pull-request CI) narrows
    # only which of them are run through the gate.
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda t: validate_cached(t, validate_task), select(tasks)))


def test_every_shipped_reference_passes_its_checks_inside_the_mutant_limit():
    """A mutant is scored dead when a check times out at MUTANT_TIMEOUT_S, so a reference check that
    is slow through the gate's comparison guard (`s in big_dict` in a loop walks the dict each time)
    kills its mutants by timeout instead of by what they got wrong. Validation's own limit is too
    loose to see this; the limit here is the one mutants are held to."""

    def slow(task):
        results = run_gate(
            task.reference_dir, task.hidden_dir, task.hidden_checks(), timeout_s=MUTANT_TIMEOUT_S
        )
        return [r.check_id for r in results if r.status is CheckStatus.TIMEOUT]

    tasks = select(load_tasks(TASKS))
    with ThreadPoolExecutor(max_workers=4) as pool:
        found = {t.id: ids for t, ids in zip(tasks, pool.map(slow, tasks), strict=True) if ids}
    assert found == {}, f"reference checks over {MUTANT_TIMEOUT_S}s through the gate: {found}"


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


@pytest.fixture
def pool(tmp_path):
    """A private two-task pool, mutants included, that a test can edit."""
    target = tmp_path / "pool"
    for name in ("slugify", "calc"):
        shutil.copytree(TASKS / name, target / name)
    return target


def test_set_digest_is_the_full_sha256_and_stable(pool):
    digest = task_set_digest(pool)
    assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")
    assert task_set_digest(pool) == digest


def test_set_digest_covers_mutants_unlike_the_set_hash(pool):
    mutant = next((pool / "slugify" / "mutants").rglob("*.py"))
    digest, short = task_set_digest(pool), task_set_hash(load_tasks(pool))
    mutant.write_bytes(mutant.read_bytes() + b"#")
    assert task_set_digest(pool) != digest
    assert task_set_hash(load_tasks(pool)) == short


def test_set_digest_changes_when_a_file_is_added_or_a_provenance_file_edited(pool):
    before = task_set_digest(pool)
    (pool / "calc" / "provenance.json").write_text("{}")
    added = task_set_digest(pool)
    (pool / "calc" / "provenance.json").write_text('{"a": 1}')
    assert len({before, added, task_set_digest(pool)}) == 3


@pytest.mark.parametrize("junk", [".DS_Store", "slugify/.hidden", "slugify/__pycache__/x.pyc"])
def test_set_digest_refuses_dotfiles_and_pycache(pool, junk):
    target = pool / junk
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    with pytest.raises(TaskError, match=r"remove it and rerun"):
        task_set_digest(pool)


def test_set_digest_refuses_a_missing_pool(tmp_path):
    with pytest.raises(TaskError, match="not a directory"):
        task_set_digest(tmp_path / "nope")


def test_set_digest_reports_an_unreadable_file_as_a_task_error(pool):
    secret = next(p for p in pool.rglob("*.py") if p.is_file())
    secret.chmod(0)
    try:
        try:
            secret.read_bytes()
        except OSError:
            pass
        else:  # root, or a filesystem that ignores modes: there is no unreadable file to test
            pytest.skip("file modes are not enforced for this user")
        with pytest.raises(TaskError, match="cannot read"):
            task_set_digest(pool)
    finally:
        secret.chmod(0o644)


def test_set_digest_refuses_a_pool_that_is_a_symlink(pool, tmp_path):
    link = tmp_path / "linked-pool"
    link.symlink_to(pool, target_is_directory=True)
    with pytest.raises(TaskError, match="is a symlink"):
        task_set_digest(link)
