"""CONTRIBUTING.md stays true: its commands, versions, rules and the benchmark-task steps."""

import re
import shutil
import subprocess
import tomllib

import pytest
from docs_support import ROOT, code_spans, read, section

from boss import boss, firm
from boss.bench import run as bench_run
from boss.bench.tasks import (
    DIFFICULTIES,
    MIN_HIDDEN_CHECKS,
    MIN_MUTANTS,
    BenchTask,
    validate_task,
)

DOC = ROOT / "CONTRIBUTING.md"
PROMPTS = ROOT / "src" / "boss" / "prompts"


@pytest.fixture(scope="module")
def text() -> str:
    return read(DOC)


def pyproject() -> dict:
    return tomllib.loads(read(ROOT / "pyproject.toml"))


def test_the_commands_ci_runs_are_the_ones_stated(text):
    workflow = read(ROOT / ".github" / "workflows" / "ci.yml")
    stated = [
        "uv sync --locked",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy",
        "uv run pytest --cov --cov-report=term-missing --cov-fail-under=96 --durations=30",
    ]
    for command in stated:
        assert command in text, f"CONTRIBUTING.md does not state: {command}"
        assert re.search(rf"^\s*run: {re.escape(command)}$", workflow, re.M), f"CI lacks: {command}"
    assert "The coverage floor is 96" in text


def test_the_only_runtime_dependency_is_the_one_stated(text):
    names = {re.split(r"[<>=!~ ]", d)[0] for d in pyproject()["project"]["dependencies"]}
    assert names == {"pytest"}, "a dependency was added: discuss it, then update CONTRIBUTING.md"
    assert "The only runtime dependency is `pytest`," in text


def test_python_version_and_line_length_stated_are_the_projects(text):
    assert "Python 3.12" in text
    assert read(ROOT / ".python-version").strip() == "3.12"
    assert pyproject()["project"]["requires-python"] == ">=3.12"
    assert pyproject()["tool"]["ruff"]["line-length"] == 100 and "line length 100" in text


def test_every_commit_type_in_the_history_is_listed(text):
    try:
        log = subprocess.run(
            ["git", "log", "--format=%s", "-n", "300"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    used = set(re.findall(r"^([a-z]+)(?:\([^)]*\))?!?: ", log, re.M))
    listed = set(code_spans(text.split("Types in use:")[1].split("The body")[0]))
    assert used <= listed, f"commit types used but not listed: {sorted(used - listed)}"


def test_prompt_files_follow_the_versioned_naming_and_the_code_names_real_ones(text):
    names = sorted(p.name for p in PROMPTS.glob("*.md"))
    assert names and all(re.fullmatch(r"[a-z_]+_v\d+\.md", n) for n in names), names
    for used in (boss.TERM_SHEET_PROMPT, boss.MULTI_TASK_PROMPT, firm.BUILDER_PROMPT):
        assert used in names
    assert "`src/boss/prompts/`" in text and "`<name>_v<N>.md`" in text


def test_gitignore_excludes_what_the_document_says(text):
    ignore = read(ROOT / ".gitignore").splitlines()
    for pattern in (".env", ".env.*", "*.pem", "*.key", ".boss/", "bench/results/raw/"):
        assert pattern in ignore and f"`{pattern}`" in text


def test_the_live_test_and_the_kn_convention_exist(text):
    live = read(ROOT / "tests" / "test_end_to_end.py")
    assert "BOSS_LIVE" in live and "BOSS_LIVE=1 uv run pytest tests/test_end_to_end.py" in text
    sources = "".join(read(p) for p in (ROOT / "src").rglob("*.py"))
    assert "# kn: " in sources and "`# kn:`" in text
    assert "(docs/BACKLOG.md)" in text and (ROOT / "docs" / "BACKLOG.md").is_file()
    assert "tests/test_backlog.py" in text and (ROOT / "tests" / "test_backlog.py").is_file()


def test_the_benchmark_task_rules_stated_are_the_validators(text):
    steps = section(text, "Add a benchmark task")
    assert f"at least {MIN_HIDDEN_CHECKS} files" in steps
    assert ", ".join(f"`{d}`" for d in DIFFICULTIES[:-1]) + f" or `{DIFFICULTIES[-1]}`" in steps
    assert "exactly the keys `id`, `title` and `difficulty`" in steps
    assert "tests/test_bench_tasks.py::test_every_shipped_task_is_valid" in steps
    assert f"at least {MIN_MUTANTS} known-wrong solutions" in steps
    assert "`mutants/<name>/`" in steps and "tests/test_bench_mutants.py" in steps


def test_a_task_built_by_those_steps_validates(tmp_path):
    root = tmp_path / "rev-task"
    (root / "hidden_checks").mkdir(parents=True)
    (root / "reference").mkdir()
    (root / "idea.md").write_text("Create rev.py with reverse(s), returning s reversed.\n")
    (root / "meta.json").write_text('{"id": "rev-task", "title": "Reverse", "difficulty": "easy"}')
    (root / "reference" / "rev.py").write_text("def reverse(s):\n    return s[::-1]\n")
    for n in range(MIN_HIDDEN_CHECKS):
        (root / "hidden_checks" / f"test_case{n}.py").write_text(
            f"from rev import reverse\n\ndef test_case():\n    assert reverse('ab{n}') == '{n}ba'\n"
        )

    def mutant(name: str, body: str) -> None:
        folder = root / "mutants" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "rev.py").write_text(f"# wrong: {name}\ndef reverse(s):\n    return {body}\n")

    for name, body in (("identity", "s"), ("upper", "s.upper()"), ("empty", "''")):
        mutant(name, body)
    task = BenchTask("rev-task", "Reverse", "easy", root)
    validate_task(task)  # raises TaskError unless every rule above holds
    mutant("empty", "s[::-1]")  # right, so not a mutant
    with pytest.raises(Exception, match="passes every hidden check"):
        validate_task(task)
    shutil.rmtree(root / "mutants" / "empty")  # two mutants are fewer than the minimum
    with pytest.raises(Exception, match=f"at least {MIN_MUTANTS} mutants"):
        validate_task(task)
    mutant("empty", "''")
    (root / "hidden_checks" / "test_case0.py").unlink()
    with pytest.raises(Exception, match="at least"):
        validate_task(task)


def test_the_dry_run_named_in_the_document_lists_cells_and_writes_nothing(tmp_path, capsys, text):
    out = tmp_path / "bench"
    args = [
        "--dry-run",
        "--out",
        str(out),
        "--budget",
        "0.40",
        "--tasks",
        str(ROOT / "bench/tasks"),
    ]
    assert bench_run.main(args) == 0
    assert "34 cells" in capsys.readouterr().out and not out.exists()
    assert "uv run python -m boss.bench.run --dry-run --out /tmp/bench --budget 0.40" in text
