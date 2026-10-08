"""The KPI scorecard: hand-built cells with known answers for every KPI and edge, the table that
renders them, the command, and old results."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from antstreet.bench import kpi
from antstreet.bench.kpi import KpiCard, build_columns, kpi_card, main, render_cards
from antstreet.bench.results import CellResult, cell_dir, load_results
from antstreet.bench.table import wilson_interval
from antstreet.ledger import Event, EventType, LedgerWriter

PASS = {"a": "passed", "b": "passed"}
FAIL = {"a": "passed", "b": "failed"}


def cell(**over: object) -> CellResult:
    fields: dict[str, object] = {
        "task": "t1",
        "arm": "firm",
        "rep": 1,
        "set_hash": "set1",
        "model": "haiku",
        "budget_micros": 400_000,
        "hidden": PASS,
        "visible_passed": 1,
        "visible_total": 1,
        "cost_micros": 0,
        "boss_micros": 0,
        "unknown_cost_events": 0,
        "outcome": "completed",
        "failure_class": None,
        "duration_s": 1.0,
    }
    fields.update(over)
    if fields["hidden"] != PASS and fields["failure_class"] is None:
        fields["failure_class"] = "model"
    return CellResult(**fields)  # type: ignore[arg-type]


def ev(actor: str, event: EventType, **data: object) -> Event:
    return Event(run="r1", round=1, actor=actor, event=event, data=data)


def asked(n: int) -> list[Event]:
    """A ledger holding exactly `n` investor questions."""
    return [ev("investor", EventType.APPROVED, hashes={}) for _ in range(n)]


def single_end(status: str) -> list[Event]:
    return [ev("worker:solo", EventType.SLICE_END, outcome="completed", status={"status": status})]


def firm_cells() -> list[CellResult]:
    return [
        # t1 has 3 runs: delivered twice, so it is not reliable
        cell(task="t1", rep=1, visible_passed=3, visible_total=3, cost_micros=100_000,
             duration_s=10, wrong_checks=1),
        cell(task="t1", rep=2, visible_passed=2, visible_total=3, cost_micros=200_000,
             duration_s=20, wrong_checks=0),  # delivered without saying done
        cell(task="t1", rep=3, hidden=FAIL, visible_passed=3, visible_total=3,
             cost_micros=300_000, duration_s=30),  # false pass: said done, a hidden check failed
        # t2 has 2 runs and held-out checks
        cell(task="t2", rep=1, visible_passed=1, visible_total=1, held_out_passed=2,
             held_out_total=2, cost_micros=50_000, duration_s=40),
        cell(task="t2", rep=2, hidden=FAIL, visible_passed=1, visible_total=1, held_out_passed=1,
             held_out_total=2, cost_micros=150_000, duration_s=50),  # held-out failed: not "done"
        # t3: infrastructure failure, left out of everything
        cell(task="t3", rep=1, hidden=FAIL, failure_class="infrastructure", cost_micros=999_999,
             duration_s=999, visible_passed=0, visible_total=3, wrong_checks=5),
        # t4: one run, said done, failed a hidden check, two events of unknown cost
        cell(task="t4", rep=1, hidden=FAIL, visible_passed=4, visible_total=4, held_out_passed=3,
             held_out_total=3, cost_micros=70_000, unknown_cost_events=2, duration_s=60),
        # t5 has 2 runs, both delivered: the only reliable task
        cell(task="t5", rep=1, visible_passed=2, visible_total=2, cost_micros=10_000, duration_s=5),
        cell(task="t5", rep=2, visible_passed=2, visible_total=2, cost_micros=10_000, duration_s=6),
    ]  # fmt: skip


def firm_ledgers() -> dict[tuple[str, str, int], list[Event]]:
    return {
        ("t1", "firm", 1): asked(1),
        ("t1", "firm", 2): asked(3),
        ("t2", "firm", 1): [*asked(1), ev("investor", EventType.RESUMED)],
        ("t3", "firm", 1): asked(5),  # infrastructure: not counted
    }


# --- the seven KPIs, each against its hand-computed answer --------------------------------------


def test_1_delivery_rate_counts_every_hidden_check_and_leaves_infrastructure_out():
    card = kpi_card(firm_cells(), firm_ledgers())
    assert (card.counted, card.delivered, card.infrastructure) == (8, 5, 1)
    assert "62% [31-86%] (5/8); 1 infrastructure excluded" in render_cards([("c", card)])
    assert wilson_interval(5, 8) == pytest.approx((0.3059, 0.8629), abs=1e-3)


def test_2_false_pass_is_said_done_and_a_hidden_check_failed_over_said_done():
    card = kpi_card(firm_cells(), firm_ledgers())
    # said done: t1r1, t1r3, t2r1, t4, t5r1, t5r2 = 6 (t1r2 missed a visible check, t2r2 a
    # held-out one); of those t1r3 and t4 failed a hidden check
    assert (card.said_done, card.false_passes) == (6, 2)
    assert "33% [10-70%] (2/6)" in render_cards([("c", card)])


def test_2_a_failed_held_out_check_stops_the_cell_from_having_said_done():
    visible_only = cell(hidden=FAIL, visible_passed=1, visible_total=1)
    held_failed = cell(
        hidden=FAIL, visible_passed=1, visible_total=1, held_out_passed=0, held_out_total=1
    )
    assert kpi_card([visible_only]).false_passes == 1
    assert kpi_card([held_failed]).said_done == 0


def test_2_no_cell_said_done_is_n_a_not_zero_percent():
    card = kpi_card([cell(hidden=FAIL, visible_passed=0, visible_total=2)])
    assert (card.said_done, card.false_passes) == (0, 0)
    assert "n/a (0 cells that said done)" in render_cards([("c", card)])


def test_2_the_single_arm_claim_is_its_last_status_word_when_a_ledger_holds_it():
    cells = [
        cell(arm="single", task="t1", rep=1, visible_passed=None, visible_total=None),
        cell(arm="single", task="t1", rep=2, hidden=FAIL, visible_passed=None, visible_total=None),
        cell(arm="single", task="t2", rep=1, hidden=FAIL, visible_passed=None, visible_total=None),
        cell(arm="single", task="t3", rep=1, visible_passed=None, visible_total=None),  # no ledger
    ]
    ledgers = {
        ("t1", "single", 1): single_end("done"),
        ("t1", "single", 2): single_end("done"),  # said done, failed a hidden check
        ("t2", "single", 1): single_end("blocked"),  # did not claim to be done
    }
    card = kpi_card(cells, ledgers)
    assert (card.said_done, card.false_passes) == (2, 1)  # the cell with no ledger is unknown


def test_2_the_single_arm_claim_is_read_from_the_result_before_the_ledger():
    single = {"arm": "single", "visible_passed": None, "visible_total": None}
    cells = [
        cell(task="t1", final_status="done", **single),  # no ledger needed
        cell(task="t2", final_status="blocked", hidden=FAIL, **single),
        # the ledger says done: the result wins
        cell(task="t3", final_status="blocked", hidden=FAIL, **single),
    ]
    card = kpi_card(cells, {("t3", "single", 1): single_end("done")})
    assert (card.said_done, card.false_passes) == (1, 0)


def test_2_a_single_result_without_the_field_falls_back_to_its_ledger_or_is_not_recorded(
    tmp_path: Path,
):
    old = cell(task="old", arm="single", visible_passed=None, visible_total=None)
    raw = asdict(old)
    del raw["final_status"]  # a result written before the field existed
    out = cell_dir(tmp_path, "old", "single", 1)
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(raw))
    assert load_results(tmp_path)[0].final_status is None
    [(_, card)] = build_columns([tmp_path])
    assert card.said_done is None  # neither the field nor a ledger
    assert "n/a (the arm's claim is not recorded)" in render_cards([("c", card)])
    write(tmp_path, old, single_end("done"))  # same cell, now with a ledger
    [(_, card)] = build_columns([tmp_path])
    assert card.said_done == 1


def test_2_final_status_is_type_checked_on_load(tmp_path: Path):
    raw = asdict(cell(arm="single", visible_passed=None, visible_total=None))
    for bad in (1, True, ["done"]):
        (tmp_path / "result.json").write_text(json.dumps(raw | {"final_status": bad}))
        with pytest.raises(ValueError, match="final_status"):
            CellResult.load(tmp_path / "result.json")


def test_2_the_single_arm_without_ledgers_is_n_a():
    card = kpi_card([cell(arm="single", visible_passed=None, visible_total=None)])
    assert card.said_done is None and card.false_passes is None
    assert "n/a (the arm's claim is not recorded)" in render_cards([("c", card)])


def test_3_cost_per_delivered_is_all_counted_spend_over_delivered_with_unknown_apart():
    card = kpi_card(firm_cells(), firm_ledgers())
    # 100+200+300+50+150+70+10+10 = 890k over 5 delivered; the infrastructure cell is excluded
    assert card.cost_micros == 890_000 and card.unknown_cost_events == 2
    shown = render_cards([("c", card)])
    assert "| 3 Cost per delivered task | $0.1780 (lower bound) |" in shown
    assert "|   events of unknown cost | 2 |" in shown


def test_3_no_delivery_means_no_cost_per_delivered():
    card = kpi_card([cell(hidden=FAIL, cost_micros=5, unknown_cost_events=1)])
    assert card.delivered == 0
    shown = render_cards([("c", card)])
    assert "| 3 Cost per delivered task | n/a (0 delivered) |" in shown
    assert "|   events of unknown cost | 1 |" in shown


def test_4_time_is_the_median_of_delivered_and_of_all_counted_cells():
    card = kpi_card(firm_cells(), firm_ledgers())
    assert card.delivered_s == 10  # delivered: 5, 6, 10, 20, 40
    assert card.counted_s == 25  # counted: 5, 6, 10, 20, 30, 40, 50, 60 -> (20 + 30) / 2
    assert "delivered 0m10s; all counted 0m25s" in render_cards([("c", card)])


def test_4_no_delivery_has_no_delivered_time():
    card = kpi_card([cell(hidden=FAIL, duration_s=90)])
    assert card.delivered_s is None and card.counted_s == 90
    assert "delivered n/a; all counted 1m30s" in render_cards([("c", card)])


def test_5_reliability_is_tasks_delivered_on_every_counted_run_and_states_k():
    cells = [cell(task=t, rep=r, hidden=h) for t, r, h in [
        ("a", 1, PASS), ("a", 2, PASS), ("a", 3, PASS),
        ("b", 1, PASS), ("b", 2, PASS), ("b", 3, FAIL),
    ]]  # fmt: skip
    card = kpi_card(cells)
    assert (card.reliable_tasks, card.tasks, card.runs_per_task) == (1, 2, ((3, 2),))
    assert "| 5 Reliability (pass^k) | 1/2 (k=3) |" in render_cards([("c", card)])


def test_5_k_that_varies_is_stated_per_k_and_a_dead_run_does_not_count():
    card = kpi_card(firm_cells(), firm_ledgers())
    # t3's only run is infrastructure, so t3 is no task at all; t1 has 3 runs, t2 2, t4 1, t5 2
    assert card.tasks == 4 and card.reliable_tasks == 1
    assert card.runs_per_task == ((1, 1), (2, 2), (3, 1))
    assert "1/4 (k varies: k=1: 1 task, k=2: 2 tasks, k=3: 1 task)" in render_cards([("c", card)])


def test_5_an_infrastructure_failure_does_not_break_a_tasks_reliability():
    cells = [
        cell(task="a", rep=1),
        cell(task="a", rep=2, hidden=FAIL, failure_class="infrastructure"),
    ]
    assert kpi_card(cells).reliable_tasks == 1


def test_6_investor_questions_per_run_from_the_ledgers_that_exist():
    card = kpi_card(firm_cells(), firm_ledgers())
    # t1r1 1 + t1r2 3 + t2r1 2 = 6 over the 3 counted cells with a ledger; the 5 asked in the
    # infrastructure cell are not counted, and 5 counted cells have no ledger
    assert (card.questions, card.question_runs) == (6, 3)
    assert "2.00 per run (6 in 3 runs); 5 runs not recorded" in render_cards([("c", card)])


def test_6_no_ledger_at_all_is_not_recorded_not_zero():
    card = kpi_card([cell()])
    assert card.question_runs == 0
    assert "| 6 Investor questions | not recorded |" in render_cards([("c", card)])


def test_6_the_single_arm_asks_zero_by_construction():
    card = kpi_card([cell(arm="single", visible_passed=None, visible_total=None)])
    assert (card.questions, card.question_runs) == (0, 1)
    assert "0 (the single arm asks none)" in render_cards([("c", card)])


def test_7_wrong_boss_checks_over_boss_checks_where_measured():
    card = kpi_card(firm_cells(), firm_ledgers())
    # measured in t1r1 (1 of 3) and t1r2 (0 of 3); the infrastructure cell's 5 are left out
    assert (card.wrong_checks, card.boss_checks) == (1, 6)
    assert "1/6 wrong (17%)" in render_cards([("c", card)])


def test_7_not_measured_and_single_arm_say_so():
    assert "| 7 Check quality | not measured |" in render_cards([("c", kpi_card([cell()]))])
    single = kpi_card([cell(arm="single", visible_passed=None, visible_total=None)])
    assert "n/a (no boss checks)" in render_cards([("c", single)])


# --- edges --------------------------------------------------------------------------------------


def test_all_infrastructure_leaves_every_figure_n_a_and_does_not_crash():
    cells = [cell(hidden=FAIL, failure_class="infrastructure", cost_micros=7) for _ in range(2)]
    card = kpi_card(cells)
    assert (card.counted, card.infrastructure, card.tasks, card.delivered) == (0, 2, 0, 0)
    shown = render_cards([("c", card)])
    assert "n/a (0 cells); 2 infrastructure excluded" in shown
    assert "n/a (0 delivered)" in shown and "n/a (0 tasks)" in shown
    assert card.cost_micros == 0 and card.counted_s is None


def test_a_card_needs_one_arm_and_some_cells():
    with pytest.raises(ValueError, match="exactly one arm"):
        kpi_card([cell(arm="firm"), cell(arm="single", visible_passed=None, visible_total=None)])
    with pytest.raises(ValueError, match="exactly one arm"):
        kpi_card([])


def test_a_cell_with_no_hidden_checks_is_not_delivered():
    assert kpi_card([cell(hidden={}, failure_class="model")]).delivered == 0


def test_the_table_has_a_row_per_kpi_a_column_per_card_and_the_overlap_line():
    shown = render_cards([("one", kpi_card(firm_cells())), ("two", kpi_card([cell()]))])
    header, rule, *rows = shown.splitlines()[:11]
    assert header == "| KPI | one | two |" and rule == "| --- | --- | --- |"
    assert [r.split(" | ")[0] for r in rows[:8]] == [
        "| 1 Delivery rate",
        "| 2 False-pass rate",
        "| 3 Cost per delivered task",
        "|   events of unknown cost",
        "| 4 Time to delivery (median)",
        "| 5 Reliability (pass^k)",
        "| 6 Investor questions",
        "| 7 Check quality",
    ]
    assert "  one: 8 cells over 4 tasks (1 excluded)" in shown
    assert "  two: 1 cells over 1 tasks (0 excluded)" in shown
    assert shown.endswith("Overlapping intervals mean no demonstrated difference.\n")


def test_two_columns_with_one_label_are_refused():
    with pytest.raises(ValueError, match="same label"):
        render_cards([("x", kpi_card([cell()])), ("x", kpi_card([cell()]))])
    with pytest.raises(ValueError, match="empty"):
        render_cards([])


def test_every_card_field_is_a_count_or_a_median_never_a_rate():
    assert KpiCard.__annotations__.keys() >= {"delivered", "said_done", "false_passes"}
    assert not any("rate" in name for name in KpiCard.__annotations__)


# --- the command, on folders written the way the runner writes them -----------------------------


def write(folder: Path, result: CellResult, ledger: list[Event] | None = None) -> None:
    out = cell_dir(folder, result.task, result.arm, result.rep)
    result.save(out)
    if ledger is not None:
        path = (
            out / "ledger.jsonl"
            if result.arm == "single"
            else out / ".boss" / "runs" / "run1" / "ledger.jsonl"
        )
        with LedgerWriter(path) as writer:
            for event in ledger:
                writer.append(event)


def test_the_command_prints_one_column_per_arm_with_ledgers_found_where_the_runner_puts_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    folder = tmp_path / "runA"
    write(folder, cell(arm="firm", rep=1), asked(2))
    write(folder, cell(arm="firm", rep=2, hidden=FAIL), asked(1))
    write(
        folder,
        cell(arm="single", rep=1, visible_passed=None, visible_total=None, hidden=FAIL),
        single_end("done"),
    )
    assert main([str(folder)]) == 0
    out = capsys.readouterr().out
    assert "| KPI | runA/firm (haiku, $0.4000) | runA/single (haiku, $0.4000) |" in out
    assert "1.50 per run (3 in 2 runs)" in out  # 2 + 1 questions over 2 runs
    # false pass: the firm's two cells both passed every visible check and one failed a hidden
    # check; the single cell said done and failed one
    assert "50% [9-91%] (1/2)" in out and "100% [21-100%] (1/1)" in out


def test_arms_from_different_folders_models_budgets_and_firm_args_get_their_own_labelled_columns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    write(tmp_path / "f", cell(arm="firm", firm_args="--slice 0.20"))
    write(tmp_path / "s", cell(arm="single", model="sonnet", budget_micros=800_000,
                               visible_passed=None, visible_total=None))  # fmt: skip
    assert main([str(tmp_path / "f"), str(tmp_path / "s")]) == 0
    out = capsys.readouterr().out
    assert "f/firm (haiku, $0.4000, --slice 0.20)" in out
    assert "s/single (sonnet, $0.8000)" in out


def test_one_folder_with_two_models_gives_two_columns(tmp_path: Path):
    write(tmp_path / "f", cell(task="a", model="haiku"))
    write(tmp_path / "f", cell(task="b", model="sonnet"))
    labels = [label for label, _ in build_columns([tmp_path / "f"])]
    assert labels == ["f/firm (haiku, $0.4000)", "f/firm (sonnet, $0.4000)"]


def test_a_column_that_would_carry_the_same_label_is_refused_not_pooled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    write(tmp_path / "a" / "x", cell(task="a"))
    write(tmp_path / "b" / "x", cell(task="a"))
    assert main([str(tmp_path / "a" / "x"), str(tmp_path / "b" / "x")]) == 1
    assert "carry the label 'x/firm (haiku, $0.4000)'" in capsys.readouterr().err
    with pytest.raises(ValueError, match="carry the label"):
        build_columns([tmp_path / "a" / "x", tmp_path / "b" / "x"])


def test_two_task_sets_in_one_folder_and_arm_are_refused_as_one_label(tmp_path: Path):
    write(tmp_path / "f", cell(task="a", set_hash="s1"))
    write(tmp_path / "f", cell(task="b", set_hash="s2"))
    with pytest.raises(ValueError, match="differ only in task set"):
        build_columns([tmp_path / "f"])


def test_an_empty_or_missing_folder_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    assert main([str(tmp_path / "nothing")]) == 1
    assert "no results found" in capsys.readouterr().err


def test_a_damaged_result_exits_1_naming_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    bad = cell_dir(tmp_path, "t1", "firm", 1)
    bad.mkdir(parents=True)
    (bad / "result.json").write_text("{not json")
    assert main([str(tmp_path)]) == 1
    assert "result.json" in capsys.readouterr().err


def test_a_damaged_or_ambiguous_ledger_is_not_recorded_not_a_crash(tmp_path: Path):
    write(tmp_path / "f", cell(task="a"), asked(1))
    broken = cell_dir(tmp_path / "f", "a", "firm", 1) / ".boss" / "runs" / "run1" / "ledger.jsonl"
    broken.write_text("not an event\n")
    write(tmp_path / "f", cell(task="b"), asked(1))
    second = cell_dir(tmp_path / "f", "b", "firm", 1) / ".boss" / "runs" / "run2"
    second.mkdir(parents=True)
    (second / "ledger.jsonl").write_text("")  # two ledgers: which one is the cell's?
    [(_, card)] = build_columns([tmp_path / "f"])
    assert (card.question_runs, card.questions) == (0, 0)


def test_the_usage_error_is_2():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


# --- old results and old ledgers ----------------------------------------------------------------


def test_results_from_before_wrong_checks_and_held_out_still_load_and_score(tmp_path: Path):
    raw = {
        "arm": "firm", "boss_micros": 60_621, "budget_micros": 400_000, "cost_micros": 299_992,
        "duration_s": 356.9, "failure_class": None, "firm_args": "--slice 0.20",
        "hidden": {"a": "passed"}, "model": "haiku", "outcome": "completed", "rep": 1,
        "set_hash": "c130282a6eec5fe8", "task": "calc", "unknown_cost_events": 0,
        "visible_passed": 7, "visible_total": 8,
    }  # fmt: skip
    out = cell_dir(tmp_path, "calc", "firm", 1)
    out.mkdir(parents=True)
    (out / "result.json").write_text(json.dumps(raw))
    [old] = load_results(tmp_path)
    assert old.wrong_checks is None and old.held_out_total is None
    card = kpi_card([old])
    assert (card.delivered, card.said_done, card.wrong_checks) == (1, 0, None)
    assert "| 7 Check quality | not measured |" in render_cards([("old", card)])


def test_a_ledger_from_before_the_chain_is_counted(tmp_path: Path):
    unchained = "\n".join(e.to_json() for e in asked(2)) + "\n"
    out = cell_dir(tmp_path, "t1", "firm", 1)
    CellResult.save(cell(), out)
    (out / ".boss" / "runs" / "run1").mkdir(parents=True)
    (out / ".boss" / "runs" / "run1" / "ledger.jsonl").write_text(unchained)
    [(_, card)] = build_columns([tmp_path])
    assert (card.questions, card.question_runs) == (2, 1)


def test_the_module_has_a_command_entry_point():
    assert callable(kpi.main)


def test_columns_that_ran_different_task_sets_are_flagged_not_compared():
    one = kpi_card([cell(set_hash="s1")])
    other = kpi_card([cell(set_hash="s2")])
    assert kpi.SETS_WARNING in render_cards([("a", one), ("b", other)])
    assert kpi.SETS_WARNING not in render_cards([("a", one), ("b", one)])


def test_a_card_with_no_measured_boss_checks_has_none_not_zero():
    card = kpi_card([cell()])
    assert card.wrong_checks is None and card.boss_checks is None


def test_boss_checks_count_only_what_was_recorded_as_a_total():
    card = kpi_card([cell(wrong_checks=1, visible_total=None), cell(task="t2", wrong_checks=0)])
    assert (card.wrong_checks, card.boss_checks) == (1, 1)


def test_the_infrastructure_note_appears_only_when_something_was_excluded():
    clean = kpi_card([cell()])
    assert "infrastructure" not in kpi._delivery(clean)
    dirty = kpi_card([cell(), cell(task="t2", failure_class="infrastructure", hidden=FAIL)])
    assert kpi._delivery(dirty).endswith("(1/1); 1 infrastructure excluded")


def test_a_half_recorded_claim_is_n_a_not_a_crash():
    import dataclasses

    card = dataclasses.replace(kpi_card([cell()]), said_done=None, false_passes=2)
    assert kpi._false_pass(card).startswith("n/a (the arm's claim is not recorded)")
    card = dataclasses.replace(kpi_card([cell()]), wrong_checks=None, boss_checks=5)
    assert kpi._check_quality(card) == "not measured"


def test_runs_without_a_recorded_question_count_are_stated_only_when_there_are_some():
    all_recorded = kpi_card([cell()], {("t1", "firm", 1): asked(2)})
    assert kpi._questions(all_recorded) == "2.00 per run (2 in 1 runs)"
    some = kpi_card([cell(), cell(task="t2")], {("t1", "firm", 1): asked(2)})
    assert kpi._questions(some) == "2.00 per run (2 in 1 runs); 1 runs not recorded"


def test_the_empty_and_the_zero_task_figures_say_n_a_with_their_reason():
    dead = kpi_card([cell(failure_class="infrastructure", hidden=FAIL)])
    assert kpi._reliability(dead) == "n/a (0 tasks)"
    single = kpi_card([cell(arm="single")])
    assert kpi._questions(single) == "0 (the single arm asks none)"
    assert kpi._check_quality(single) == "n/a (no boss checks)"


def test_the_table_is_refused_when_empty_or_when_labels_repeat_and_says_so():
    with pytest.raises(ValueError, match="cannot render an empty scorecard"):
        render_cards([])
    card = kpi_card([cell()])
    with pytest.raises(ValueError, match="same label: a, a, b, b$"):
        render_cards([("b", card), ("a", card), ("a", card), ("b", card)])


def test_the_table_ends_with_the_sample_sizes_a_blank_line_and_the_note():
    card = kpi_card([cell()])
    text = render_cards([("x", card)])
    assert (
        "\n\nSample sizes (counted cells over tasks; infrastructure failures excluded):\n" in text
    )
    assert text.endswith("\n  x: 1 cells over 1 tasks (0 excluded)\n\n" + kpi.NOTE + "\n")
    mixed = render_cards([("x", card), ("y", kpi_card([cell(set_hash="other")]))])
    assert mixed.startswith(kpi.SETS_WARNING + "\n\n")


def test_the_command_says_no_results_found_and_prints_the_table_without_extra_newline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    (tmp_path / "empty").mkdir()
    assert main([str(tmp_path / "empty")]) == 1
    assert "no results found" in capsys.readouterr().err
    c = cell()
    c.save(cell_dir(tmp_path / "run", c.task, c.arm, c.rep))
    assert main([str(tmp_path / "run")]) == 0
    assert capsys.readouterr().out.endswith(kpi.NOTE + "\n")


def _forged_firm_cell(root: Path) -> Path:
    """A firm cell whose run was signed, with a `check_result passed` appended without the key."""
    from antstreet.rundir import RunPaths

    run = RunPaths(root / ".boss" / "runs" / "r1")
    with run.writer() as ledger:
        ledger.append(Event(run="r1", round=1, actor="gate", event=EventType.CHECK_RESULT,
                            data={"check": "c01", "status": "failed"}))  # fmt: skip
    with LedgerWriter(run.ledger) as ledger:
        ledger.append(Event(run="r1", round=1, actor="gate", event=EventType.CHECK_RESULT,
                            data={"check": "c01", "status": "passed"}))  # fmt: skip
    return root


def test_a_firm_ledger_is_read_with_its_project_key_so_a_keyless_append_is_not_counted(tmp_path):
    assert kpi.load_ledger(_forged_firm_cell(tmp_path / "cell")) is None
    plain = tmp_path / "single"  # the single arm's ledger has no project and no key to check
    with LedgerWriter(plain / "ledger.jsonl") as ledger:
        ledger.append(Event(run="r1", round=1, actor="worker:solo", event=EventType.SLICE_START))
    assert kpi.load_ledger(plain) is not None
