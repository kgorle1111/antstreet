from __future__ import annotations

import json
from pathlib import Path

import pytest

from antstreet.bench.results import CellResult, cell_dir
from antstreet.bench.table import (
    CLOSING,
    MIXED_WARNING,
    main,
    per_task,
    render_table,
    summarize,
    wilson_interval,
)

PASS = {"a": "passed", "b": "passed"}
HALF = {"a": "passed", "b": "failed"}
NONE = {"a": "failed", "b": "failed"}


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
    if fields["hidden"] != PASS and fields["failure_class"] is None:
        fields["failure_class"] = "product"
    return CellResult(**fields)  # type: ignore[arg-type]


def single_set() -> list[CellResult]:
    return [
        cell(task="t1", rep=0, hidden=PASS, cost_micros=1_000_000, unknown_cost_events=1),
        cell(task="t1", rep=1, hidden=HALF, cost_micros=3_000_000, unknown_cost_events=2),
        cell(task="t2", rep=0, hidden=NONE, cost_micros=2_000_000),
        cell(
            task="t2",
            rep=1,
            hidden={},
            cost_micros=9_000_000,
            unknown_cost_events=5,
            failure_class="infrastructure",
        ),
    ]


def test_wilson_known_values() -> None:
    low, high = wilson_interval(7, 10)
    assert low == pytest.approx(0.3968, abs=1e-3)
    assert high == pytest.approx(0.8922, abs=1e-3)


def test_wilson_edges() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)
    low, high = wilson_interval(0, 5)
    assert low == 0.0
    assert high == pytest.approx(0.4345, abs=1e-3)
    low, high = wilson_interval(5, 5)
    assert high == 1.0
    assert low == pytest.approx(0.5655, abs=1e-3)


def test_infrastructure_excluded_from_rates_but_counted() -> None:
    (s,) = summarize(single_set())
    assert (s.cells, s.infrastructure, s.tasks) == (3, 1, 2)
    assert s.unknown_cost_events == 3  # the excluded cell's 5 events do not count


def test_rates_and_costs_hand_worked() -> None:
    (s,) = summarize(single_set())
    assert s.passed == 1
    assert s.pass_rate == pytest.approx(1 / 3)
    assert (s.pass_low, s.pass_high) == pytest.approx(wilson_interval(1, 3))
    assert s.check_rate == pytest.approx((1 + 0.5 + 0) / 3)
    assert s.mean_cost_micros == pytest.approx(2_000_000)  # (1M + 3M + 2M) / 3
    assert s.cost_per_pass_micros == pytest.approx(6_000_000)  # all known spend / 1 pass


def test_cost_per_pass_none_when_nothing_passed() -> None:
    (s,) = summarize([cell(hidden=NONE), cell(rep=1, hidden=HALF)])
    assert s.passed == 0
    assert s.cost_per_pass_micros is None


def test_arm_with_only_infrastructure_cells() -> None:
    (s,) = summarize([cell(hidden={}, failure_class="infrastructure")])
    assert (s.cells, s.infrastructure, s.pass_rate) == (0, 1, 0.0)
    assert (s.pass_low, s.pass_high) == (0.0, 1.0)
    assert s.mean_cost_micros == 0.0
    assert s.cost_per_pass_micros is None


def test_boss_share() -> None:
    firm = [
        cell(arm="firm", cost_micros=4_000_000, boss_micros=1_000_000),
        cell(arm="firm", rep=1, cost_micros=6_000_000, boss_micros=2_000_000),
    ]
    (s,) = summarize(firm)
    assert s.boss_share == pytest.approx(0.3)


def test_boss_share_zero_when_no_cost() -> None:
    (s,) = summarize([cell(cost_micros=0)])
    assert s.boss_share == 0.0


def test_visible_and_gamed_for_firm_only() -> None:
    firm = [
        cell(arm="firm", rep=0, hidden=PASS, visible_passed=3, visible_total=3),
        cell(arm="firm", rep=1, hidden=HALF, visible_passed=3, visible_total=3),
        cell(arm="firm", rep=2, hidden=HALF, visible_passed=2, visible_total=3),
        cell(arm="firm", rep=3, hidden=HALF, visible_passed=0, visible_total=0),
    ]
    single, firm_s = summarize([cell(), *firm])
    assert (single.visible_pass_cells, single.gamed_cells) == (None, None)
    assert (firm_s.visible_pass_cells, firm_s.gamed_cells) == (2, 1)


def test_summaries_follow_arm_order_and_skip_absent_arms() -> None:
    both = [cell(arm="firm"), cell(arm="single")]
    assert [s.arm for s in summarize(both)] == ["single", "firm"]
    assert [s.arm for s in summarize([cell(arm="firm")])] == ["firm"]


def test_per_task_ordering_and_counts() -> None:
    results = [
        cell(task="b", arm="single", hidden=PASS),
        cell(task="a", arm="firm", hidden=HALF),
        cell(task="a", arm="single", rep=0, hidden=PASS),
        cell(task="a", arm="single", rep=1, hidden=NONE),
        cell(task="c", arm="single", hidden={}, failure_class="infrastructure"),
    ]
    assert per_task(results) == [
        ("a", {"single": (1, 2), "firm": (0, 1)}),
        ("b", {"single": (1, 1)}),
        ("c", {"single": (0, 0)}),
    ]


def test_render_single_arm_exact_row_and_no_firm_line() -> None:
    text = render_table(single_set())
    assert text.startswith("Task set: set1 | Model: m1 | Budget per cell: $1.0000\n")
    row = (
        "| single | 3 | 2 | 1 | 33% [6-79%] | 50% | $2.0000 | $6.0000 | 0% | 3 | 1 | 0m01s | 0/2 |"
    )
    assert row in text
    assert "| t1 | 1/2 |" in text
    assert "| t2 | 0/1 |" in text
    assert "Visible vs hidden" not in text
    assert MIXED_WARNING not in text


def test_render_n_a_when_nothing_passed() -> None:
    text = render_table([cell(hidden=NONE)])
    assert (
        "| single | 1 | 1 | 0 | 0% [0-79%] | 0% | $1.0000 | n/a | 0% | 0 | 0 | 0m01s | 0/1 |"
        in text
    )


def test_render_n_a_cost_when_only_infrastructure() -> None:
    text = render_table([cell(hidden={}, failure_class="infrastructure")])
    assert "| single | 0 | 0 | 0 | 0% [0-100%] | 0% | n/a | n/a | 0% | 0 | 1 |" in text


def test_render_firm_visible_vs_hidden_line() -> None:
    firm = [
        cell(arm="firm", rep=0, hidden=PASS, visible_passed=3, visible_total=3),
        cell(arm="firm", rep=1, hidden=HALF, visible_passed=3, visible_total=3),
        cell(arm="firm", rep=2, hidden=HALF, visible_passed=1, visible_total=3),
    ]
    text = render_table([cell(), *firm])
    assert (
        "Visible vs hidden: 2 of 3 firm cells passed every visible check; "
        "1 of those failed a hidden check.\n"
    ) in text
    assert "| task | single | firm |" in text


def test_closing_line_always_present() -> None:
    assert CLOSING in render_table([cell()])
    assert render_table([cell()]).rstrip().endswith(CLOSING)


@pytest.mark.parametrize(
    "other",
    [
        {"set_hash": "set2"},
        {"model": "m2"},
        {"budget_micros": 2_000_000},
    ],
)
def test_mixed_results_warn_and_list_every_value(other: dict[str, object]) -> None:
    text = render_table([cell(), cell(rep=1, **other)])
    assert MIXED_WARNING in text
    assert text.splitlines()[1] == MIXED_WARNING


def test_mixed_header_lists_all_values() -> None:
    text = render_table([cell(), cell(rep=1, set_hash="set2", model="m2", budget_micros=2_000_000)])
    assert text.splitlines()[0] == (
        "Task set: set1, set2 | Model: m1, m2 | Budget per cell: $1.0000, $2.0000"
    )


def test_render_empty_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        render_table([])


def _save(root: Path, r: CellResult) -> None:
    r.save(cell_dir(root, r.task, r.arm, r.rep))


def test_main_prints_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _save(tmp_path, cell())
    assert main([str(tmp_path)]) == 0
    assert "| single | 1 | 1 | 1 | 100% [21-100%] |" in capsys.readouterr().out


def test_main_writes_out_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _save(tmp_path / "res", cell())
    out = tmp_path / "table.md"
    assert main([str(tmp_path / "res"), "--out", str(out)]) == 0
    assert capsys.readouterr().out == ""
    assert out.read_text(encoding="utf-8").endswith(CLOSING + "\n")


def test_main_empty_folder_returns_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no results found" in captured.err


def firm_cell(wrong: int | None, total: int = 8, **over: object) -> CellResult:
    return cell(arm="firm", visible_passed=total, visible_total=total, wrong_checks=wrong, **over)


def test_wrong_checks_are_summed_over_the_cells_where_they_were_measured() -> None:
    results = [
        firm_cell(0, task="t1"),
        firm_cell(3, task="t2"),
        firm_cell(1, total=7, task="t3"),
        firm_cell(None, task="t4"),  # an older result: not measured, so not counted as zero
    ]
    [firm] = summarize(results)
    assert (firm.wrong_checks, firm.boss_checks, firm.wrong_check_cells) == (4, 23, 2)
    assert (
        "Wrong boss checks: 4 of 23 checks failed on the reference solution, in 2 drafts."
        in render_table(results)
    )


def test_no_wrong_check_line_when_nothing_was_measured_or_for_the_single_arm() -> None:
    [firm] = summarize([firm_cell(None)])
    assert (firm.wrong_checks, firm.boss_checks, firm.wrong_check_cells) == (None, None, None)
    assert "Wrong boss checks" not in render_table([firm_cell(None)])
    [single] = summarize(single_set())
    assert single.wrong_checks is None
    assert "Wrong boss checks" not in render_table(single_set())


def test_an_infrastructure_cell_does_not_add_to_the_wrong_check_count() -> None:
    results = [
        firm_cell(1, task="t1"),
        firm_cell(5, task="t2", hidden={}, failure_class="infrastructure"),
    ]
    [firm] = summarize(results)
    assert (firm.wrong_checks, firm.boss_checks) == (1, 8)


def test_results_written_before_the_wrong_check_field_still_load(tmp_path: Path) -> None:
    old = firm_cell(None)
    old.save(tmp_path)
    raw = json.loads((tmp_path / "result.json").read_text())
    del raw["wrong_checks"]
    (tmp_path / "result.json").write_text(json.dumps(raw))
    assert CellResult.load(tmp_path / "result.json").wrong_checks is None
    raw["wrong_checks"] = "two"
    (tmp_path / "result.json").write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="wrong_checks"):
        CellResult.load(tmp_path / "result.json")


def test_time_is_the_median_of_counted_cells_and_ignores_infrastructure() -> None:
    cells = [
        cell(rep=0, duration_s=60.0),
        cell(rep=1, duration_s=125.4),
        cell(rep=2, duration_s=9000.0),
        cell(rep=3, duration_s=1.0, hidden={}, failure_class="infrastructure"),
    ]
    [s] = summarize(cells)
    assert s.median_duration_s == 125.4  # not the mean, which one slow cell would drag
    assert "| 2m05s | 1/1 |" in render_table(cells)


def test_a_task_counts_as_reliable_only_when_every_counted_run_passed() -> None:
    cells = [
        cell(task="t1", rep=0),
        cell(task="t1", rep=1),
        cell(task="t2", rep=0),
        cell(task="t2", rep=1, hidden=HALF),
        cell(task="t3", rep=0),
        cell(task="t3", rep=1, hidden={}, failure_class="infrastructure"),
    ]
    [s] = summarize(cells)
    assert (s.passed, s.cells, s.reliable_tasks, s.tasks) == (4, 5, 2, 3)  # t1 and t3


def test_an_arm_with_only_infrastructure_cells_has_no_time() -> None:
    [s] = summarize([cell(hidden={}, failure_class="infrastructure")])
    assert s.median_duration_s is None and s.reliable_tasks == 0
    assert "| n/a | 0/0 |" in render_table([cell(hidden={}, failure_class="infrastructure")])


def held_cell(wrong: int | None, total: int | None = 3, **over: object) -> CellResult:
    return firm_cell(
        0,
        held_out_wrong=wrong,
        held_out_passed=None if total is None else 0,
        held_out_total=total,
        **over,
    )


def test_wrong_held_out_checks_are_summed_over_the_cells_where_they_were_measured() -> None:
    results = [
        held_cell(0, task="t1"),
        held_cell(2, task="t2"),
        held_cell(1, total=2, task="t3"),
        held_cell(None, task="t4"),  # an older result: not measured, so not counted as zero
        held_cell(4, task="t5", hidden={}, failure_class="infrastructure"),
    ]
    [firm] = summarize(results)
    assert (firm.held_out_wrong, firm.held_out_checks, firm.held_out_wrong_cells) == (3, 8, 2)
    assert (
        "Wrong held-out checks: 3 of 8 checks failed on the reference solution, in 2 cells."
        in render_table(results)
    )


def test_no_wrong_held_out_line_when_nothing_was_measured_or_for_the_single_arm() -> None:
    [firm] = summarize([held_cell(None)])
    assert firm.held_out_wrong is None and firm.held_out_wrong_cells is None
    assert "Wrong held-out checks" not in render_table([held_cell(None)])
    [single] = summarize(single_set())
    assert single.held_out_wrong is None
    assert "Wrong held-out checks" not in render_table(single_set())


def test_the_table_has_the_published_columns_and_blank_lines_between_its_parts() -> None:
    lines = render_table(single_set()).split("\n")
    assert lines[1] == ""
    assert lines[2] == (
        "| arm | cells | tasks | passed | pass rate [95% CI] | hidden checks | mean cost/cell"
        " | cost/pass | boss share | unknown-cost events | infrastructure excluded"
        " | median time/cell | tasks passed every run |"
    )
    assert lines[3] == "| " + " | ".join(["---"] * 13) + " |"
    assert lines[-4:] == ["| t2 | 0/1 |", "", CLOSING, ""]
    assert lines[5] == "" and lines[6] == "| task | single |"


def test_a_percentage_is_rounded_from_the_rate_not_from_a_scaled_one() -> None:
    results = [cell(task=f"t{i}", rep=0) for i in range(40)]
    assert "100% [91-100%]" in render_table(results)


def test_cost_per_pass_is_the_cost_divided_by_the_cells_that_passed() -> None:
    results = [
        cell(task="t1", cost_micros=3_000_000),
        cell(task="t2", cost_micros=3_000_000),
        cell(task="t3", hidden=NONE, cost_micros=0),
    ]
    assert summarize(results)[0].cost_per_pass_micros == 3_000_000


def test_a_boss_check_total_that_was_not_recorded_counts_as_zero_checks() -> None:
    firm = [
        cell(arm="firm", visible_passed=1, visible_total=None, wrong_checks=1),
        cell(arm="firm", task="t2", visible_passed=2, visible_total=2, wrong_checks=0),
    ]
    assert summarize(firm)[0].boss_checks == 2


def test_held_out_figures_are_none_until_a_cell_measured_them_and_skip_missing_totals() -> None:
    assert summarize([cell(arm="firm")])[0].held_out_checks is None
    held = [
        cell(arm="firm", held_out_wrong=1, held_out_total=None),
        cell(arm="firm", task="t2", held_out_wrong=0, held_out_passed=3, held_out_total=3),
    ]
    assert summarize(held)[0].held_out_checks == 3


def test_one_visible_check_passed_counts_as_every_visible_check_passed() -> None:
    s = summarize([cell(arm="firm", visible_passed=1, visible_total=1)])[0]
    assert s.visible_pass_cells == 1


def test_an_empty_table_says_why_and_stdout_is_exactly_the_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(ValueError, match="cannot tabulate an empty result set"):
        render_table([])
    _save(tmp_path, cell())
    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.endswith(CLOSING + "\n") and not out.endswith("\n\n")


def test_the_command_is_named_and_its_out_option_says_what_it_does() -> None:
    from docs_support import captured_parser

    parser = captured_parser(main)
    assert parser.prog == "python -m antstreet.bench.table"
    out = next(a for a in parser._actions if "--out" in a.option_strings)
    assert out.help == "write the table here instead of stdout"
