"""Benchmark result edge cases: invariants, hand-edited files, and result discovery."""

import dataclasses
import json
from pathlib import Path

import pytest

from boss.bench.results import (
    ARMS,
    FAILURE_CLASSES,
    RESULT_FILE,
    CellResult,
    cell_dir,
    load_results,
)

PASSING = {"h1": "passed", "h2": "passed"}


def cell(**overrides) -> CellResult:
    base = {
        "task": "slugify",
        "arm": "single",
        "rep": 1,
        "set_hash": "abc",
        "model": "haiku",
        "budget_micros": 500_000,
        "hidden": PASSING,
        "visible_passed": None,
        "visible_total": None,
        "cost_micros": 1000,
        "boss_micros": 0,
        "unknown_cost_events": 0,
        "outcome": "completed",
        "failure_class": None,
        "duration_s": 1.5,
    }
    return CellResult(**(base | overrides))


# --- invariants -----------------------------------------------------------------------------


@pytest.mark.parametrize("arm", ["", "Single", "both", "firm "])
def test_only_the_two_known_arms_are_accepted(arm):
    with pytest.raises(ValueError, match="arm must be one of"):
        cell(arm=arm)


@pytest.mark.parametrize("arm", ARMS)
def test_both_arms_are_accepted(arm):
    assert cell(arm=arm).arm == arm


def test_unknown_failure_class_is_refused_and_named():
    with pytest.raises(ValueError, match="unknown failure class 'flaky'"):
        cell(hidden={"h1": "failed"}, failure_class="flaky")


@pytest.mark.parametrize("failure_class", FAILURE_CLASSES)
def test_every_documented_failure_class_is_accepted_on_a_failing_cell(failure_class):
    assert cell(hidden={"h1": "failed"}, failure_class=failure_class).failure_class == failure_class


def test_a_passing_cell_cannot_carry_a_failure_class():
    with pytest.raises(ValueError, match="a passing cell cannot have a failure class"):
        cell(failure_class="model")


def test_the_unknown_class_check_runs_before_the_passing_check():
    with pytest.raises(ValueError, match="unknown failure class"):
        cell(failure_class="nonsense")


def test_a_failing_cell_may_leave_its_failure_class_unset():
    assert cell(hidden={"h1": "failed"}).failure_class is None


# --- derived values -------------------------------------------------------------------------


def test_counts_and_pass_flag_follow_the_hidden_statuses():
    mixed = cell(hidden={"a": "passed", "b": "failed", "c": "timeout", "d": "passed"})
    assert (mixed.hidden_passed, mixed.hidden_total, mixed.passed) == (2, 4, False)
    assert cell().passed is True


def test_a_cell_with_no_hidden_checks_never_passes():
    empty = cell(hidden={})
    assert (empty.hidden_passed, empty.hidden_total, empty.passed) == (0, 0, False)


def test_only_the_exact_string_passed_counts():
    odd = cell(hidden={"a": "Passed", "b": "pass", "c": "passed"}, failure_class="model")
    assert odd.hidden_passed == 1 and not odd.passed


# --- save and load --------------------------------------------------------------------------


def test_save_creates_missing_parent_folders_and_round_trips(tmp_path):
    target = tmp_path / "deep" / "er" / "cell"
    original = cell(firm_args="--rounds 3", visible_passed=2, visible_total=3, duration_s=0.25)
    original.save(target)
    assert CellResult.load(target / RESULT_FILE) == original


def test_saved_json_is_sorted_and_indented_for_diffs(tmp_path):
    cell().save(tmp_path)
    text = (tmp_path / RESULT_FILE).read_text()
    keys = list(json.loads(text))
    assert keys == sorted(keys)
    assert text.startswith('{\n  "arm": "single"')


def test_saving_again_overwrites_the_previous_result(tmp_path):
    cell(cost_micros=1).save(tmp_path)
    cell(cost_micros=2).save(tmp_path)
    assert CellResult.load(tmp_path / RESULT_FILE).cost_micros == 2


def test_a_result_saved_before_firm_args_existed_still_loads(tmp_path):
    raw = dataclasses.asdict(cell())
    del raw["firm_args"]
    (tmp_path / RESULT_FILE).write_text(json.dumps(raw))
    assert CellResult.load(tmp_path / RESULT_FILE).firm_args == ""


def test_hand_labelling_a_failure_class_in_the_file_is_honoured_on_load(tmp_path):
    raw = dataclasses.asdict(cell(hidden={"h1": "failed"}))
    raw["failure_class"] = "grading"
    (tmp_path / RESULT_FILE).write_text(json.dumps(raw))
    assert CellResult.load(tmp_path / RESULT_FILE).failure_class == "grading"


def test_a_hand_edit_that_breaks_an_invariant_is_refused_on_load(tmp_path):
    raw = dataclasses.asdict(cell())
    raw["failure_class"] = "model"  # a passing cell cannot be blamed on anything
    (tmp_path / RESULT_FILE).write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="passing cell cannot have a failure class"):
        CellResult.load(tmp_path / RESULT_FILE)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("task"),
        lambda d: d.pop("hidden"),
        lambda d: d.update(surprise=1),
    ],
    ids=["missing-required", "missing-hidden", "unknown-field"],
)
def test_wrong_field_sets_name_the_file(tmp_path, mutate):
    raw = dataclasses.asdict(cell())
    mutate(raw)
    path = tmp_path / RESULT_FILE
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match=f"{path}: fields differ from the result schema"):
        CellResult.load(path)


@pytest.mark.parametrize("text", ["[]", "null", '"cell"', "3"])
def test_a_result_file_that_is_not_an_object_is_refused(tmp_path, text):
    path = tmp_path / RESULT_FILE
    path.write_text(text)
    with pytest.raises(ValueError, match="fields differ from the result schema"):
        CellResult.load(path)


@pytest.mark.parametrize(
    "payload", [b"", b"{", b'{"task": "\xff"}'], ids=["empty", "torn", "bytes"]
)
def test_unreadable_result_files_raise_value_errors(tmp_path, payload):
    path = tmp_path / RESULT_FILE
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        CellResult.load(path)


def test_a_missing_result_file_is_an_os_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        CellResult.load(tmp_path / RESULT_FILE)


def test_a_hidden_field_of_the_wrong_type_is_refused_on_load(tmp_path):
    raw = dataclasses.asdict(cell())
    raw["hidden"] = ["h1", "h2"]
    path = tmp_path / RESULT_FILE
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        CellResult.load(path)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("hidden", ["h1"]),
        ("hidden", {"h1": 1}),
        ("rep", "1"),
        ("rep", True),
        ("cost_micros", 1.5),
        ("visible_passed", "2"),
        ("outcome", None),
        ("duration_s", "fast"),
    ],
)
def test_a_wrongly_typed_field_is_refused_naming_the_file_and_field(tmp_path, name, value):
    raw = dataclasses.asdict(cell()) | {name: value}
    path = tmp_path / RESULT_FILE
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError) as info:
        CellResult.load(path)
    assert str(path) in str(info.value)
    assert name in str(info.value)


# --- cell_dir and load_results --------------------------------------------------------------


def test_cell_dir_layout():
    assert cell_dir(Path("results"), "slugify", "firm", 3) == Path("results/slugify/firm/rep3")


def test_load_results_orders_by_path_and_round_trips_every_cell(tmp_path):
    cells = [
        cell(task="b-task", arm="firm", rep=1),
        cell(task="a-task", arm="single", rep=2),
        cell(task="a-task", arm="firm", rep=1),
        cell(task="a-task", arm="single", rep=10),
        cell(task="a-task", arm="single", rep=1),
    ]
    for c in cells:
        c.save(cell_dir(tmp_path, c.task, c.arm, c.rep))
    loaded = load_results(tmp_path)
    assert [(c.task, c.arm, c.rep) for c in loaded] == [
        ("a-task", "firm", 1),
        ("a-task", "single", 1),
        ("a-task", "single", 10),  # path order: rep1 < rep10 < rep2
        ("a-task", "single", 2),
        ("b-task", "firm", 1),
    ]


def test_load_results_ignores_files_that_are_not_cell_results(tmp_path):
    cell().save(cell_dir(tmp_path, "t", "single", 1))
    (tmp_path / "t" / "single" / "rep1" / "notes.json").write_text("{")
    (tmp_path / "t" / "single" / "scratch").mkdir()
    (tmp_path / "t" / "single" / "scratch" / RESULT_FILE).write_text("{")
    (tmp_path / "stray").mkdir()
    (tmp_path / "stray" / RESULT_FILE).write_text("{")
    assert len(load_results(tmp_path)) == 1


def test_a_missing_results_folder_means_no_results(tmp_path):
    assert load_results(tmp_path / "nope") == []


def test_one_corrupt_result_fails_the_whole_load_instead_of_being_skipped(tmp_path):
    cell().save(cell_dir(tmp_path, "t", "single", 1))
    bad = cell_dir(tmp_path, "t", "firm", 1)
    bad.mkdir(parents=True)
    (bad / RESULT_FILE).write_text("{")
    with pytest.raises(ValueError):
        load_results(tmp_path)
