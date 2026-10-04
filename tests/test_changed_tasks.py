"""CI validates only the benchmark tasks a pull request changed, and never skips by mistake."""

import subprocess
from pathlib import Path

import pytest
from changed_tasks import ENV_VAR, changed_task_ids, select


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo, check=True, capture_output=True,
    )  # fmt: skip


def commit(repo: Path, files: dict[str, str], message: str) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    commit(
        tmp_path,
        {
            "bench/tasks/a/idea.md": "a",
            "bench/tasks/b/idea.md": "b",
            "bench/tasks-multi/m/idea.md": "m",
            "src/x.py": "x",
        },
        "base",
    )
    git(tmp_path, "tag", "base")
    monkeypatch.setenv(ENV_VAR, "base")
    return tmp_path


class Task:
    def __init__(self, id: str):
        self.id = id


def test_without_the_variable_every_task_is_validated(repo, monkeypatch):
    commit(repo, {"bench/tasks/a/idea.md": "changed"}, "touch a")
    monkeypatch.delenv(ENV_VAR)
    assert changed_task_ids(repo) is None
    tasks = [Task("a"), Task("b")]
    assert select(tasks, repo) == tasks


def test_only_the_tasks_with_changed_files_are_selected(repo):
    commit(
        repo,
        {
            "bench/tasks/a/mutants/m1/f.py": "new mutant",
            "bench/tasks-multi/m/idea.md": "changed",
            "src/x.py": "not a task",
        },
        "touch a and m",
    )
    assert changed_task_ids(repo) == {"a", "m"}
    assert [t.id for t in select([Task("a"), Task("b"), Task("m")], repo)] == ["a", "m"]


def test_a_branch_with_no_task_changes_selects_none(repo):
    commit(repo, {"src/x.py": "changed"}, "not a task")
    assert changed_task_ids(repo) == set()


def test_an_added_and_a_deleted_task_are_named(repo):
    commit(repo, {"bench/tasks/new/idea.md": "n"}, "add")
    (repo / "bench/tasks/b/idea.md").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "delete b")
    assert changed_task_ids(repo) == {"new", "b"}


@pytest.mark.parametrize("ref", ["no-such-ref", "--output=oops", "  ", "base..main"])
def test_an_unusable_ref_validates_everything(repo, monkeypatch, ref):
    commit(repo, {"bench/tasks/a/idea.md": "changed"}, "touch a")
    monkeypatch.setenv(ENV_VAR, ref)
    assert changed_task_ids(repo) is None


def test_a_file_that_belongs_to_no_single_task_validates_everything(repo):
    commit(repo, {"bench/tasks/README.md": "shared"}, "shared file")
    assert changed_task_ids(repo) is None


def test_outside_a_git_checkout_everything_is_validated(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, "origin/main")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert changed_task_ids(tmp_path) is None
