"""Imported tasks: a spec plus an external pytest tree, converted, validated and graded per test.

Everything here is a tiny synthetic task written for these tests; no external benchmark data is
ever copied into the repository.
"""

import json
import os
import shutil
from pathlib import Path

import pytest
from test_bench_run import FAKE_CLAUDE  # the fake `claude` that plays boss and worker

from antstreet.bench.imported import ConvertError, convert_nl2repo, main
from antstreet.bench.results import CellResult, load_results
from antstreet.bench.run import main as run_main
from antstreet.bench.run import run_cell
from antstreet.bench.table import render_table
from antstreet.bench.tasks import (
    BenchTask,
    TaskError,
    grade_imported,
    load_task,
    load_tasks,
    task_set_hash,
    validate_task,
)

# A spec may embed code; both arms see it equally.
SPEC = """# widget

Create `widget.py` with `widget(text)` that returns the text upper-cased.

```python
def test_demo():
    assert widget("a") == "A"
```
"""
TEST_A = """import os

from mock import patch

from widget import widget

HERE = os.path.dirname(__file__)


def test_upper():
    assert widget("ab") == "AB"


def test_reads_the_data_file():
    with open(os.path.join(HERE, "data", "words.txt")) as f:
        assert widget(f.readline().strip()) == "ALPHA"


def test_mock_is_importable():
    with patch("widget.widget", return_value="x"):
        import widget as module

        assert module.widget("a") == "x"
"""
TEST_B = """import pytest

from widget import widget


@pytest.mark.parametrize("text,n", [("a", 1), ("bcd", 3)])
def test_length(text, n):
    assert len(widget(text)) == n


def test_strip():
    assert widget(" ab ") == "AB"
"""
UPPER = "def widget(text):\n    return text.upper()\n"
STRIPPED = "def widget(text):\n    return text.strip().upper()\n"
# What the partial product passes: everything except test_strip.
FAILS = {"tests/test_b.py::test_strip"}
NODES = {
    "tests/test_a.py::test_upper",
    "tests/test_a.py::test_reads_the_data_file",
    "tests/test_a.py::test_mock_is_importable",
    "tests/test_b.py::test_length[a-1]",
    "tests/test_b.py::test_length[bcd-3]",
    "tests/test_b.py::test_strip",
}


def make_source(root: Path) -> Path:
    """A downloaded task folder as the converter expects it."""
    src = root / "widget"
    (src / "tests" / "data").mkdir(parents=True)
    (src / "start.md").write_text(SPEC)
    (src / "tests" / "__init__.py").write_text("")
    (src / "tests" / "test_a.py").write_text(TEST_A)
    (src / "tests" / "test_b.py").write_text(TEST_B)
    (src / "tests" / "data" / "words.txt").write_text("alpha\nbeta\n")
    (src / "test_commands.json").write_text(
        json.dumps(["pip install -e .", "pytest --continue-on-collection-errors tests"])
    )
    (src / "test_case_count.txt").write_text("6")
    return src


@pytest.fixture
def task(tmp_path) -> BenchTask:
    dest = convert_nl2repo(make_source(tmp_path), tmp_path / "tasks")
    return load_task(dest)


def problems(task: BenchTask) -> list[str]:
    with pytest.raises(TaskError) as info:
        validate_task(task)
    return info.value.problems


def product(tmp_path: Path, source: str | None, name: str = "prod") -> Path:
    folder = tmp_path / name
    folder.mkdir()
    if source is not None:
        (folder / "widget.py").write_text(source)
    return folder


# --- the converter and the format -------------------------------------------------------------


def test_the_converter_lays_out_an_imported_task_that_validates(task):
    assert (task.id, task.difficulty) == ("widget", "hard")
    assert (task.imported.source, task.imported.test_path, task.imported.test_count) == (
        "nl2repo",
        "tests",
        6,
    )
    assert task.idea == SPEC.strip()
    assert (task.hidden_dir / "data" / "words.txt").read_text() == "alpha\nbeta\n"
    assert (task.hidden_dir / "__init__.py").is_file()
    assert not (task.root / "reference").exists() and task.hidden_checks() == []
    validate_task(task)  # no reference, no mutants, an idea with `def test_` in it: all fine


def test_a_third_party_import_the_gate_lacks_gets_a_support_shim(task):
    assert (task.support_dir / "mock.py").read_text().startswith("from unittest.mock import *")
    shutil.rmtree(task.support_dir)
    assert any("'mock'" in p for p in problems(task))


def test_no_shim_is_written_when_no_test_needs_one(tmp_path):
    src = make_source(tmp_path)
    for name in ("test_a.py", "test_b.py"):
        (src / "tests" / name).write_text("def test_x():\n    pass\n")
    (src / "test_case_count.txt").write_text("2")
    assert not (convert_nl2repo(src, tmp_path / "t") / "support").exists()


def test_the_converter_never_overwrites_and_names_what_is_wrong(tmp_path):
    src = make_source(tmp_path)
    convert_nl2repo(src, tmp_path / "t")
    with pytest.raises(ConvertError, match="already exists"):
        convert_nl2repo(src, tmp_path / "t")
    (src / "test_case_count.txt").write_text("many")
    with pytest.raises(ConvertError, match="one whole number"):
        convert_nl2repo(src, tmp_path / "t2")
    (src / "test_case_count.txt").write_text("6")
    (src / "test_commands.json").write_text('["pip install -e ."]')
    with pytest.raises(ConvertError, match="exactly one `pytest"):
        convert_nl2repo(src, tmp_path / "t2")
    (src / "test_commands.json").write_text('["pytest nowhere"]')
    with pytest.raises(ConvertError, match="not a folder"):
        convert_nl2repo(src, tmp_path / "t2")
    assert not (tmp_path / "t2").exists()


def test_the_converter_command_prints_validity_and_exits_zero(tmp_path, capsys):
    assert main(["nl2repo", str(make_source(tmp_path)), str(tmp_path / "t")]) == 0
    assert "task widget is valid" in capsys.readouterr().out
    assert main(["nl2repo", str(tmp_path / "widget"), str(tmp_path / "t")]) == 1
    assert "already exists" in capsys.readouterr().err


def test_a_wrong_expected_count_is_reported(task):
    meta = json.loads((task.root / "meta.json").read_text())
    meta["imported"]["test_count"] = 7
    (task.root / "meta.json").write_text(json.dumps(meta))
    assert "hidden/ defines 6 tests but imported.test_count says 7" in problems(
        load_task(task.root)
    )


def test_a_hidden_file_that_does_not_parse_or_a_symlink_is_reported(task):
    (task.hidden_dir / "test_c.py").write_text("def broken(:\n")
    (task.hidden_dir / "link.txt").symlink_to(task.hidden_dir / "test_a.py")
    found = problems(task)
    assert any(p.startswith("hidden/test_c.py does not parse") for p in found)
    assert "hidden/link.txt is a symlink; the tree must be plain files" in found


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("source", "elsewhere", "imported.source must be one of"),
        ("test_path", "../x", "imported.test_path must be a relative path"),
        ("test_path", "/abs", "imported.test_path must be a relative path"),
    ],
)
def test_bad_imported_meta_is_reported(task, key, value, message):
    meta = json.loads((task.root / "meta.json").read_text())
    meta["imported"][key] = value
    (task.root / "meta.json").write_text(json.dumps(meta))
    assert any(message in p for p in problems(load_task(task.root)))


@pytest.mark.parametrize(
    "imported",
    [
        {},
        {"source": "nl2repo", "test_path": "tests"},
        "x",
        {"source": "nl2repo", "test_path": "t", "test_count": 0},
    ],
)
def test_a_malformed_imported_block_is_refused_at_load(task, imported):
    meta = json.loads((task.root / "meta.json").read_text())
    meta["imported"] = imported
    (task.root / "meta.json").write_text(json.dumps(meta))
    with pytest.raises(TaskError, match="imported"):
        load_task(task.root)


def test_a_suite_that_passes_on_an_empty_product_is_rejected(task):
    (task.hidden_dir / "test_free.py").write_text("def test_free():\n    pass\n")
    meta = json.loads((task.root / "meta.json").read_text())
    meta["imported"]["test_count"] = 7
    (task.root / "meta.json").write_text(json.dumps(meta))
    assert "1 hidden tests pass on an empty product" in problems(load_task(task.root))


def test_the_idea_still_may_not_start_with_a_dash(task):
    (task.root / "idea.md").write_text("-rf spec")
    assert "idea.md must not start with '-'" in problems(task)


def test_the_set_hash_covers_the_hidden_tree_and_the_support_files(task):
    before = task_set_hash([task])
    (task.hidden_dir / "data" / "words.txt").write_text("gamma\n")
    assert task_set_hash([task]) != before
    (task.hidden_dir / "data" / "words.txt").write_text("alpha\nbeta\n")
    assert task_set_hash([task]) == before
    (task.support_dir / "mock.py").write_text("# other\n")
    assert task_set_hash([task]) != before


# --- grading ---------------------------------------------------------------------------------


def test_grading_records_every_test_by_node_id(task, tmp_path):
    hidden = grade_imported(task, product(tmp_path, UPPER))
    assert hidden == {n: "failed" if n in FAILS else "passed" for n in NODES}


def test_a_product_that_passes_everything_passes_every_test(task, tmp_path):
    assert (
        set(grade_imported(task, product(tmp_path, "def widget(text):\n    return 'AB'\n")))
        == NODES
    )
    hidden = grade_imported(task, product(tmp_path, STRIPPED, "p2"))
    assert hidden["tests/test_b.py::test_strip"] == "passed"


def test_an_empty_or_missing_product_fails_all_tests_and_is_padded_to_the_expected_count(
    task, tmp_path
):
    for workspace in (product(tmp_path, None), tmp_path / "never-made"):
        hidden = grade_imported(task, workspace)
        assert len(hidden) == 6 and set(hidden.values()) == {"failed"}


def test_lost_tests_count_as_failures_against_the_expected_count(task, tmp_path):
    # An import error loses a whole file's tests: one error entry stands for them, and the rest
    # of the 6 are filled in as failed, so the pass fraction is over the suite.
    broken = product(tmp_path, "def widget(text:\n")
    hidden = grade_imported(task, broken)
    assert len(hidden) == 6 and set(hidden.values()) == {"failed"}
    assert "(not run 1)" in hidden


def test_the_product_cannot_plant_its_own_tests_or_a_shim_over_the_hidden_ones(task, tmp_path):
    folder = product(tmp_path, UPPER)
    (folder / "tests").mkdir()
    (folder / "tests" / "conftest.py").write_text("raise SystemExit('planted')\n")
    (folder / "tests" / "test_planted.py").write_text("def test_planted():\n    pass\n")
    (folder / "mock.py").write_text("raise SystemExit('shadowed')\n")
    hidden = grade_imported(task, folder)
    assert set(hidden) == NODES  # the product's own tests/ is replaced, its mock.py overridden
    assert {n for n, s in hidden.items() if s == "failed"} == FAILS
    assert sorted(p.name for p in (folder / "tests").iterdir()) == [
        "conftest.py",
        "test_planted.py",
    ]


def test_grading_leaves_the_product_untouched(task, tmp_path):
    folder = product(tmp_path, UPPER)
    before = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*"))
    grade_imported(task, folder)
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")) == before


# --- a cell, the table, and what the workers see ---------------------------------------------


@pytest.fixture
def bench(tmp_path, task):
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE.replace("slugify", "widget"))
    fake.chmod(0o755)
    environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
    results = tmp_path / "results"

    def cell(arm, source=UPPER, rep=1) -> CellResult:
        (tmp_path / "product.py").write_text(source)
        return run_cell(
            task, arm, rep, results, environ=environ, set_hash="abc123", budget_micros=400_000
        )

    cell.home, cell.results = tmp_path, results
    cell.calls = lambda: [
        json.loads(line) for line in (tmp_path / "argv.log").read_text().splitlines()
    ]
    return cell


def test_both_arms_record_the_per_test_map_and_a_partial_pass_is_not_a_pass(bench):
    for arm in ("single", "firm"):
        result = bench(arm)
        assert result.hidden == {n: "failed" if n in FAILS else "passed" for n in NODES}
        assert (result.hidden_passed, result.hidden_total) == (5, 6)
        assert not result.passed and result.failure_class == "unlabelled"
    assert bench("firm").wrong_checks is None  # there is no reference to judge the boss's checks
    full = bench("single", STRIPPED, rep=2)
    assert full.passed and full.hidden_total == 6


def test_the_table_shows_the_pass_fraction_per_test(bench):
    bench("single")
    bench("firm")
    bench("single", STRIPPED, rep=2)
    table = render_table(load_results(bench.results))
    single = next(line for line in table.splitlines() if line.startswith("| single"))
    cells = [c.strip() for c in single.strip("|").split("|")]
    # 5/6 and 6/6 of the tests: a mean per-test pass fraction of 92%, one cell of two passing.
    assert cells[3] == "1" and cells[5] == "92%"


def test_hidden_tests_support_files_and_node_ids_never_reach_a_prompt_or_a_workspace(bench, task):
    bench("single")
    bench("firm")
    prompts = json.dumps(bench.calls())
    for path in sorted(p for p in task.hidden_dir.rglob("*") if p.is_file()):
        assert path.name not in prompts or path.name == "__init__.py"
        if path.suffix == ".py" and path.read_text().strip():
            assert path.read_text().strip() not in prompts
    for node in NODES:
        assert node not in prompts
    assert "words.txt" not in prompts and "unittest.mock" not in prompts
    workspace_files = {
        p.relative_to(bench.results).parts[-1]
        for p in bench.results.rglob("*")
        if p.is_file() and {"workspace", "workspaces"} & set(p.parts)
    }
    assert workspace_files == {"widget.py"}


def test_the_runner_validates_an_imported_task_and_lists_its_cells(tmp_path, task, capsys):
    tasks = task.root.parent
    out = tmp_path / "out"
    argv = ["--tasks", str(tasks), "--out", str(out), "--budget", "0.80", "--arms", "single"]
    assert run_main([*argv, "--dry-run"], environ=os.environ) == 0
    assert "widget single rep1" in capsys.readouterr().out
    assert [t.id for t in load_tasks(tasks)] == ["widget"]


def test_method_states_the_format_and_command_the_code_uses():
    text = (Path(__file__).parent.parent / "bench" / "METHOD.md").read_text()
    body = text.split("## Imported tasks")[1].split("\n## ")[0]
    for term in ("`hidden/`", "`support/`", "`idea.md`", "`imported`", "`test_count`"):
        assert term in body
    assert "python -m antstreet.bench.imported nl2repo <task-dir> <dest-root>" in body
    assert "Not comparable with the external leaderboard" in body
    assert "--continue-on-collection-errors" in body
