"""Replay edge cases: damaged ledgers, degenerate histories, and the real rule end to end."""

from pathlib import Path

import pytest

from antstreet.bench.replay import (
    CLOSING,
    WorkerReplay,
    main,
    render_replay,
    replay_runs,
    replay_worker,
)
from antstreet.errors import Outcome
from antstreet.ledger import Event, EventType, LedgerWriter
from antstreet.rule import Decision, FiringPolicy, SliceRecord, Verdict, decide

STALL2 = FiringPolicy(stall_slices=2, max_slices=6)


def rec(n, cost, *passing, outcome=Outcome.COMPLETED) -> SliceRecord:
    return SliceRecord(n, cost, outcome, "continuing", frozenset(passing))


def ev(actor, event, run="r1", **fields) -> Event:
    return Event(run=run, round=1, actor=actor, event=event, **fields)


def worker_events(worker, checks, slices, run="r1") -> list[Event]:
    out = [ev("boss", EventType.HIRED, run, data={"worker": worker, "task": "t1"})]
    for n, (cost, passing) in enumerate(slices, start=1):
        end = {"slice": n, "task": "t1", "outcome": "completed", "status": {"status": "continuing"}}
        out.append(ev(f"worker:{worker}", EventType.SLICE_END, run, cost_micros=cost, data=end))
        for c in sorted(checks):
            data = {"check": c, "task": "t1", "worker": worker, "slice": n}
            data["status"] = "passed" if c in passing else "failed"
            out.append(ev("gate", EventType.CHECK_RESULT, run, data=data))
    return out


def write_ledger(path: Path, events: list[Event]) -> None:
    with LedgerWriter(path) as w:
        for e in events:
            w.append(e)


def never_fire(checks, history, policy):
    return Verdict(Decision.CONTINUE, "stub")


def fire_at(n):
    def decide_stub(checks, history, policy):
        return Verdict(Decision.FIRE if len(history) == n else Decision.CONTINUE, "stub")

    return decide_stub


# --- replay_worker --------------------------------------------------------------------------


def test_an_empty_history_is_never_fired_and_never_asks_the_rule():
    def explode(*_):
        raise AssertionError("decide must not run")

    assert replay_worker("w", frozenset({"a"}), [], STALL2, explode) == WorkerReplay(
        "w", 0, None, 0, False, False
    )


def test_firing_after_the_last_slice_saves_nothing_and_is_not_a_false_firing():
    history = [rec(1, 100, "a"), rec(2, 200)]
    result = replay_worker("w", frozenset({"a", "b"}), history, STALL2, fire_at(2))
    assert (result.fired_after, result.saved_micros) == (2, 0)
    assert (result.false_firing, result.lost_completion) == (False, False)


def test_a_later_slice_passing_only_checks_already_passed_is_not_a_false_firing():
    history = [rec(1, 100, "a"), rec(2, 100, "a"), rec(3, 100, "a")]
    result = replay_worker("w", frozenset({"a", "b"}), history, STALL2, fire_at(2))
    assert (result.false_firing, result.saved_micros) == (False, 100)


def test_a_regression_then_recovery_of_an_old_check_is_not_a_false_firing():
    history = [rec(1, 1, "a"), rec(2, 1), rec(3, 1, "a")]
    result = replay_worker("w", frozenset({"a", "b"}), history, STALL2, fire_at(2))
    assert result.false_firing is False


def test_a_task_with_no_checks_can_never_be_a_lost_completion():
    history = [rec(1, 1), rec(2, 1, "a")]
    result = replay_worker("w", frozenset(), history, STALL2, fire_at(1))
    assert result.lost_completion is False
    assert result.false_firing is True


def test_the_slice_number_reported_is_the_records_number_even_when_it_is_not_the_index():
    history = [rec(4, 1), rec(5, 1), rec(6, 1)]
    result = replay_worker("w", frozenset({"a"}), history, STALL2, fire_at(2))
    assert result.fired_after == 5 and result.slices == 3


def test_the_first_fire_wins_and_later_ones_are_not_consulted():
    calls = []

    def always_fire(checks, history, policy):
        calls.append(len(history))
        return Verdict(Decision.FIRE, "stub")

    replay_worker("w", frozenset({"a"}), [rec(1, 1), rec(2, 1)], STALL2, always_fire)
    assert calls == [1]


def test_the_real_rule_fires_a_stalled_worker_and_flags_the_late_completion():
    history = [rec(1, 1000), rec(2, 1000), rec(3, 1000), rec(4, 1000, "a", "b")]
    result = replay_worker("w", frozenset({"a", "b"}), history, STALL2, decide)
    assert result == WorkerReplay(
        worker="w",
        slices=4,
        fired_after=2,
        saved_micros=2000,
        false_firing=True,
        lost_completion=True,
    )


def test_infrastructure_slices_do_not_count_toward_the_real_rules_stall():
    infra = Outcome.RATE_LIMITED
    history = [rec(1, 10), rec(2, 10, outcome=infra), rec(3, 10, outcome=infra)]
    assert replay_worker("w", frozenset({"a"}), history, STALL2, decide).fired_after is None


# --- replay_runs ----------------------------------------------------------------------------


def test_no_policies_means_no_results():
    assert replay_runs([worker_events("w", {"a"}, [(1, {"a"})])], []) == []


def test_no_runs_gives_zero_workers_and_zero_totals_per_policy():
    [result] = replay_runs([], [STALL2], never_fire)
    assert (result.workers, result.fired, result.saved_micros, result.total_micros) == (0, 0, 0, 0)


def test_a_worker_with_slices_but_no_check_results_is_excluded_from_everything():
    events = [
        ev("boss", EventType.HIRED, data={"worker": "w", "task": "t1"}),
        ev(
            "worker:w",
            EventType.SLICE_END,
            cost_micros=500,
            data={"slice": 1, "outcome": "completed"},
        ),
    ]
    [result] = replay_runs([events], [STALL2], never_fire)
    assert (result.workers, result.total_micros) == (0, 0)


def test_the_same_worker_name_in_two_runs_is_two_workers():
    run1 = worker_events("w1", {"a"}, [(100, {"a"})], run="r1")
    run2 = worker_events("w1", {"a"}, [(200, set())], run="r2")
    [result] = replay_runs([run1, run2], [STALL2], never_fire)
    assert (result.workers, result.total_micros) == (2, 300)


def test_total_cost_is_the_same_for_every_policy_and_ignores_unknown_costs():
    events = worker_events("w", {"a"}, [(100, set()), (None, set()), (300, set())])
    results = replay_runs([events], [FiringPolicy(1, 6), FiringPolicy(3, 6)], decide)
    assert [r.total_micros for r in results] == [400, 400]
    assert [r.saved_micros for r in results] == [400 - 100, 0]


def test_results_keep_the_order_of_the_policies_given():
    policies = [FiringPolicy(3, 6), FiringPolicy(1, 4), FiringPolicy(2, 8)]
    results = replay_runs([worker_events("w", {"a"}, [(1, set())])], policies, never_fire)
    assert [r.policy for r in results] == policies


# --- rendering ------------------------------------------------------------------------------


def test_render_with_no_results_is_just_the_header_and_the_closing_line():
    assert render_replay([]).splitlines() == [
        "| stall | max slices | workers | fired | false firings | lost completions | saved |",
        "|---|---|---|---|---|---|---|",
        "",
        CLOSING,
    ]


def test_render_shows_one_decimal_percentages_and_four_decimal_dollars():
    events = worker_events("w", {"a"}, [(1_000_000, set()), (2_000_000, set()), (1_000_000, set())])
    [result] = replay_runs([events], [FiringPolicy(1, 6)], decide)
    row = render_replay([result]).splitlines()[2]
    assert row == "| 1 | 6 | 1 | 1 | 0 (0.0%) | 0 | $3.0000 (75.0%) |"


# --- main -----------------------------------------------------------------------------------


def test_a_missing_results_folder_is_reported_not_raised(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == 1
    assert "no ledger with slice data under" in capsys.readouterr().err


def test_a_ledger_with_a_slice_but_no_checks_prints_a_zero_worker_table(tmp_path, capsys):
    write_ledger(
        tmp_path / "ledger.jsonl",
        [
            ev(
                "worker:w",
                EventType.SLICE_END,
                cost_micros=5,
                data={"slice": 1, "outcome": "completed"},
            )
        ],
    )
    assert main([str(tmp_path), "--stall", "2", "--max-slices", "6"], decide=never_fire) == 0
    assert "| 2 | 6 | 0 | 0 | 0 (n/a) | 0 | $0.0000 (n/a) |" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--stall", "--max-slices"])
@pytest.mark.parametrize("value", ["0", "-2"])
def test_policy_values_below_one_exit_2_with_the_reason_on_stderr(tmp_path, capsys, flag, value):
    write_ledger(tmp_path / "ledger.jsonl", worker_events("w", {"a"}, [(1, set())]))
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), flag, value], decide=never_fire)
    assert exc.value.code == 2
    assert "must be at least 1" in capsys.readouterr().err


def test_non_numeric_policy_values_exit_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--stall", "many"], decide=never_fire)
    assert exc.value.code == 2


def test_ledgers_that_are_valid_but_have_no_slices_are_skipped_silently(tmp_path, capsys):
    write_ledger(tmp_path / "empty" / "ledger.jsonl", [ev("boss", EventType.BOSS_CALL)])
    write_ledger(tmp_path / "real" / "ledger.jsonl", worker_events("w", {"a"}, [(7, set())]))
    assert main([str(tmp_path), "--stall", "1", "--max-slices", "4"], decide=never_fire) == 0
    assert "| 1 | 4 | 1 | 0 |" in capsys.readouterr().out


def test_a_torn_ledger_is_reported_with_its_path_not_a_traceback(tmp_path, capsys):
    path = tmp_path / "ledger.jsonl"
    write_ledger(path, worker_events("w", {"a"}, [(1, set())]))
    with path.open("a") as fh:
        fh.write('{"v": 1, "run": ')
    assert main([str(tmp_path)], decide=never_fire) == 1
    assert "ledger.jsonl" in capsys.readouterr().err


def test_a_ledger_that_is_not_utf8_is_reported_with_its_path(tmp_path, capsys):
    (tmp_path / "ledger.jsonl").write_bytes(b"\xff\xfe\n")
    assert main([str(tmp_path)], decide=never_fire) == 1
    assert "ledger.jsonl" in capsys.readouterr().err
