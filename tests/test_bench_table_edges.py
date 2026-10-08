"""Table edge cases: statistics at the extremes, awkward result sets, and the command line."""

from pathlib import Path

import pytest

from antstreet.bench.results import RESULT_FILE, CellResult, cell_dir
from antstreet.bench.table import (
    MIXED_WARNING,
    main,
    per_task,
    render_table,
    summarize,
    wilson_interval,
)

PASS = {"a": "passed", "b": "passed"}
FAIL = {"a": "failed", "b": "failed"}


def cell(**over: object) -> CellResult:
    fields: dict[str, object] = {
        "task": "t1",
        "arm": "single",
        "rep": 0,
        "set_hash": "set1",
        "model": "m1",
        "budget_micros": 1_000_000,
        "hidden": PASS,
        "visible_passed": None,
        "visible_total": None,
        "cost_micros": 1_000_000,
        "boss_micros": 0,
        "unknown_cost_events": 0,
        "outcome": "done",
        "failure_class": None,
        "duration_s": 1.0,
    }
    fields.update(over)
    hidden = fields["hidden"]
    all_passed = bool(hidden) and all(v == "passed" for v in hidden.values())  # type: ignore[union-attr]
    if not all_passed and fields["failure_class"] is None:
        fields["failure_class"] = "product"
    return CellResult(**fields)  # type: ignore[arg-type]


def save(root: Path, r: CellResult) -> None:
    r.save(cell_dir(root, r.task, r.arm, r.rep))


# --- Wilson interval ------------------------------------------------------------------------


@pytest.mark.parametrize("n", [1, 2, 5, 20, 100])
def test_interval_always_contains_the_observed_rate_and_stays_in_bounds(n):
    for successes in range(n + 1):
        low, high = wilson_interval(successes, n)
        assert 0.0 <= low <= successes / n <= high <= 1.0


@pytest.mark.parametrize("n", [1, 5, 50])
def test_all_or_nothing_pins_the_matching_bound(n):
    assert wilson_interval(0, n)[0] == 0.0
    assert wilson_interval(n, n)[1] == 1.0
    assert wilson_interval(0, n)[1] > 0.0
    assert wilson_interval(n, n)[0] < 1.0


def test_more_data_narrows_the_interval():
    def width(n):
        low, high = wilson_interval(n // 2, n)
        return high - low

    assert width(10) > width(100) > width(1000)


def test_a_wider_z_gives_a_wider_interval():
    narrow = wilson_interval(5, 10, z=1.0)
    wide = wilson_interval(5, 10, z=2.58)
    assert wide[0] < narrow[0] and wide[1] > narrow[1]


def test_interval_is_symmetric_around_one_half():
    low, high = wilson_interval(3, 10)
    mirror_low, mirror_high = wilson_interval(7, 10)
    assert (low, high) == pytest.approx((1 - mirror_high, 1 - mirror_low))


# --- summaries ------------------------------------------------------------------------------


def test_a_single_passing_cell_is_a_full_pass_rate_with_a_wide_interval():
    [s] = summarize([cell()])
    assert (s.cells, s.passed, s.pass_rate, s.tasks) == (1, 1, 1.0, 1)
    assert s.pass_high == 1.0 and s.pass_low < 0.25


def test_check_rate_averages_per_cell_not_over_all_checks():
    results = [
        cell(rep=0, hidden={"a": "passed"}),  # passes: 1/1
        cell(rep=1, hidden={"a": "passed", "b": "failed", "c": "failed", "d": "failed"}),
    ]
    [s] = summarize(results)
    assert s.check_rate == pytest.approx((1.0 + 0.25) / 2)


def test_a_cell_with_no_hidden_checks_counts_as_a_zero_check_rate_not_an_error():
    [s] = summarize([cell(rep=0), cell(rep=1, hidden={}, failure_class="grading")])
    assert s.check_rate == pytest.approx(0.5)
    assert s.passed == 1 and s.cells == 2


def test_cost_per_pass_spreads_the_spend_of_failed_cells_over_the_passes():
    results = [
        cell(rep=0, cost_micros=1_000_000),
        cell(rep=1, hidden=FAIL, cost_micros=3_000_000),
    ]
    [s] = summarize(results)
    assert s.cost_per_pass_micros == 4_000_000
    assert s.mean_cost_micros == 2_000_000


def test_unknown_cost_events_are_summed_over_counted_cells_only():
    results = [
        cell(rep=0, unknown_cost_events=2),
        cell(rep=1, hidden=FAIL, unknown_cost_events=3),
        cell(rep=2, hidden=FAIL, failure_class="infrastructure", unknown_cost_events=9),
    ]
    [s] = summarize(results)
    assert (s.unknown_cost_events, s.cells, s.infrastructure) == (5, 2, 1)


def test_visible_pass_needs_a_positive_total():
    firm = [
        cell(arm="firm", rep=0, visible_passed=0, visible_total=0),
        cell(arm="firm", rep=1, visible_passed=2, visible_total=2),
        cell(arm="firm", rep=2, visible_passed=None, visible_total=None),
        cell(arm="firm", rep=3, visible_passed=1, visible_total=2),
    ]
    [s] = summarize(firm)
    assert s.visible_pass_cells == 1
    assert s.gamed_cells == 0


def test_a_gamed_cell_is_a_visible_pass_that_failed_hidden():
    firm = [
        cell(arm="firm", rep=0, visible_passed=2, visible_total=2, hidden=FAIL),
        cell(arm="firm", rep=1, visible_passed=2, visible_total=2),
    ]
    [s] = summarize(firm)
    assert (s.visible_pass_cells, s.gamed_cells) == (2, 1)


def test_the_single_arm_has_no_visible_columns():
    [s] = summarize([cell()])
    assert (s.visible_pass_cells, s.gamed_cells) == (None, None)


def test_tasks_counts_distinct_counted_tasks_only():
    results = [
        cell(task="a", rep=0),
        cell(task="a", rep=1),
        cell(task="b", hidden=FAIL, failure_class="infrastructure"),
    ]
    [s] = summarize(results)
    assert s.tasks == 1


def test_per_task_shows_a_task_that_only_hit_infrastructure_as_zero_of_zero():
    results = [cell(task="only-infra", hidden=FAIL, failure_class="infrastructure")]
    assert per_task(results) == [("only-infra", {"single": (0, 0)})]


def test_per_task_omits_an_arm_that_never_ran_the_task():
    results = [cell(task="a", arm="single"), cell(task="b", arm="firm")]
    assert per_task(results) == [("a", {"single": (1, 1)}), ("b", {"firm": (1, 1)})]


# --- rendering ------------------------------------------------------------------------------


def test_render_uses_a_dash_for_a_task_one_arm_did_not_run():
    text = render_table([cell(task="a", arm="single"), cell(task="b", arm="firm", rep=0)])
    assert "| a | 1/1 | - |" in text
    assert "| b | - | 1/1 |" in text


@pytest.mark.parametrize(
    "field",
    [{"set_hash": "set2"}, {"model": "m2"}, {"budget_micros": 2_000_000}],
    ids=["set", "model", "budget"],
)
def test_the_warning_sits_directly_under_the_header_line(field):
    text = render_table([cell(rep=0), cell(rep=1, **field)])
    lines = text.splitlines()
    assert lines[1] == MIXED_WARNING
    assert lines[2] == ""


def test_identical_settings_produce_no_warning_and_a_single_value_each():
    text = render_table([cell(rep=0), cell(rep=1)])
    assert text.splitlines()[0] == "Task set: set1 | Model: m1 | Budget per cell: $1.0000"
    assert MIXED_WARNING not in text


def test_a_mixed_header_lists_values_sorted_and_deduplicated():
    text = render_table([cell(rep=0, model="zed"), cell(rep=1, model="alpha"), cell(rep=2)])
    assert "Model: alpha, m1, zed" in text.splitlines()[0]


def test_the_table_ends_with_exactly_one_newline():
    text = render_table([cell()])
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_infrastructure_only_results_render_without_dividing_by_zero():
    text = render_table([cell(hidden=FAIL, failure_class="infrastructure")])
    row = next(line for line in text.splitlines() if line.startswith("| single"))
    assert row == "| single | 0 | 0 | 0 | 0% [0-100%] | 0% | n/a | n/a | 0% | 0 | 1 | n/a | 0/0 |"


# --- main -----------------------------------------------------------------------------------


def test_main_writes_the_out_file_in_utf8_and_prints_nothing(tmp_path, capsys):
    save(tmp_path / "res", cell(task="tést"))
    out = tmp_path / "table.md"
    assert main([str(tmp_path / "res"), "--out", str(out)]) == 0
    assert "tést" in out.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""


def test_main_out_into_a_missing_folder_is_an_os_error(tmp_path):
    save(tmp_path / "res", cell())
    with pytest.raises(FileNotFoundError):
        main([str(tmp_path / "res"), "--out", str(tmp_path / "no" / "table.md")])


def test_main_on_a_missing_folder_says_so(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == 1
    assert f"no results found under {tmp_path / 'nope'}" in capsys.readouterr().err


def test_main_ignores_stray_files_next_to_results(tmp_path, capsys):
    save(tmp_path, cell())
    (tmp_path / "t1" / "single" / "rep0" / "notes.txt").write_text("hello")
    (tmp_path / "README.md").write_text("hi")
    assert main([str(tmp_path)]) == 0
    assert "| single | 1 |" in capsys.readouterr().out


def test_main_reports_a_damaged_result_file_by_name(tmp_path, capsys):
    save(tmp_path, cell())
    bad = cell_dir(tmp_path, "t2", "single", 0)
    bad.mkdir(parents=True)
    (bad / RESULT_FILE).write_text("{")
    assert main([str(tmp_path)]) == 1
    assert "t2" in capsys.readouterr().err


def test_main_reports_a_result_file_that_is_not_utf8_by_name(tmp_path, capsys):
    bad = cell_dir(tmp_path, "t2", "single", 0)
    bad.mkdir(parents=True)
    (bad / RESULT_FILE).write_bytes(b"\xff\xfe")
    assert main([str(tmp_path)]) == 1
    assert "t2" in capsys.readouterr().err
