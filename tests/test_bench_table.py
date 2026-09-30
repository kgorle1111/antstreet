from __future__ import annotations

from pathlib import Path

import pytest

from boss.bench.results import CellResult, cell_dir
from boss.bench.table import (
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
    assert "| single | 3 | 2 | 1 | 33% [6-79%] | 50% | $2.0000 | $6.0000 | 0% | 3 | 1 |" in text
    assert "| t1 | 1/2 |" in text
    assert "| t2 | 0/1 |" in text
    assert "Visible vs hidden" not in text
    assert MIXED_WARNING not in text


def test_render_n_a_when_nothing_passed() -> None:
    text = render_table([cell(hidden=NONE)])
    assert "| single | 1 | 1 | 0 | 0% [0-79%] | 0% | $1.0000 | n/a | 0% | 0 | 0 |" in text


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
