from pathlib import Path

import pytest

from boss.bench.replay import (
    PolicyResult,
    WorkerReplay,
    main,
    render_replay,
    replay_runs,
    replay_worker,
    task_checks_by_worker,
)
from boss.errors import Outcome
from boss.ledger import Event, EventType, LedgerWriter
from boss.rule import Decision, FiringPolicy, SliceRecord, Verdict


def stall_decide(checks, history, policy):
    """FIRE when the last `stall_slices` records added no check beyond the earlier ones."""
    seen = frozenset().union(*(r.passing for r in history[: -policy.stall_slices]))
    recent = frozenset().union(*(r.passing for r in history[-policy.stall_slices :]))
    fire = len(history) >= policy.stall_slices and recent <= seen
    return Verdict(Decision.FIRE if fire else Decision.CONTINUE, "test stub")


def rec(n, cost, *passing) -> SliceRecord:
    return SliceRecord(n, cost, Outcome.COMPLETED, "continuing", frozenset(passing))


def ev(actor, event, run="r1", **fields) -> Event:
    return Event(run=run, round=1, actor=actor, event=event, **fields)


def worker_events(worker, checks, slices, run="r1") -> list[Event]:
    """One hired event, then per slice a slice_end and a check_result for every task check."""
    out = [ev("boss", EventType.HIRED, run, data={"worker": worker, "task": "t1"})]
    for n, (cost, passing) in enumerate(slices, start=1):
        end = {"slice": n, "task": "t1", "outcome": "completed", "status": {"status": "continuing"}}
        out.append(ev(f"worker:{worker}", EventType.SLICE_END, run, cost_micros=cost, data=end))
        for c in sorted(checks):
            data = {"check": c, "task": "t1", "worker": worker, "slice": n}
            data["status"] = "passed" if c in passing else "failed"
            out.append(ev("gate", EventType.CHECK_RESULT, run, data=data))
    return out


STALL1 = FiringPolicy(stall_slices=1, max_slices=6)
STALL2 = FiringPolicy(stall_slices=2, max_slices=6)


def test_task_checks_by_worker_takes_every_status_and_ignores_untagged():
    events = worker_events("w1", {"c1", "c2"}, [(1, {"c1"})])
    events.append(ev("gate", EventType.CHECK_RESULT, data={"check": "c9", "status": "passed"}))
    events += worker_events("w2", {"c3"}, [(1, set())])
    assert task_checks_by_worker(events) == {"w1": {"c1", "c2"}, "w2": {"c3"}}


def test_worker_that_keeps_progressing_is_never_fired():
    history = [rec(1, 1_000, "c1"), rec(2, 2_000, "c1", "c2")]
    got = replay_worker("w", frozenset({"c1", "c2", "c3"}), history, STALL1, stall_decide)
    assert got == WorkerReplay("w", 2, None, 0, False, False)


def test_fired_worker_whose_later_slices_made_no_progress_saves_their_cost():
    history = [rec(1, 1_000, "c1"), rec(2, 2_000, "c1"), rec(3, 3_000, "c1"), rec(4, 4_000, "c1")]
    got = replay_worker("w", frozenset({"c1", "c2"}), history, STALL1, stall_decide)
    assert got == WorkerReplay("w", 4, 2, 7_000, False, False)


def test_later_slice_passing_a_new_check_is_a_false_firing():
    history = [rec(1, 1_000, "c1"), rec(2, 2_000, "c1"), rec(3, 3_000, "c1", "c2")]
    got = replay_worker("w", frozenset({"c1", "c2", "c3"}), history, STALL1, stall_decide)
    assert got == WorkerReplay("w", 3, 2, 3_000, True, False)


def test_a_check_passed_before_the_firing_point_is_not_new():
    history = [rec(1, 1_000, "c1"), rec(2, 1_000, "c2"), rec(3, 1_000), rec(4, 1_000, "c1")]
    got = replay_worker("w", frozenset({"c1", "c2", "c3"}), history, STALL1, stall_decide)
    assert (got.fired_after, got.false_firing) == (3, False)


def test_later_slice_with_every_check_passing_is_a_lost_completion():
    history = [rec(1, 1_000, "c1"), rec(2, 2_000, "c1"), rec(3, 3_000, "c1", "c2")]
    got = replay_worker("w", frozenset({"c1", "c2"}), history, STALL1, stall_decide)
    assert got == WorkerReplay("w", 3, 2, 3_000, True, True)


def test_fired_after_is_the_slice_number_not_the_index():
    history = [rec(4, 1_000, "c1"), rec(5, 1_000, "c1")]
    assert replay_worker("w", frozenset({"c1"}), history, STALL1, stall_decide).fired_after == 5


def test_unknown_costs_count_as_zero():
    history = [rec(1, 1_000, "c1"), rec(2, None, "c1"), rec(3, None, "c1"), rec(4, 500, "c1")]
    got = replay_worker("w", frozenset({"c1", "c2"}), history, STALL1, stall_decide)
    assert (got.fired_after, got.saved_micros) == (2, 500)


def test_decide_sees_growing_prefixes_and_stops_at_first_fire():
    seen: list[int] = []

    def decide(checks, history, policy):
        seen.append(len(history))
        return Verdict(Decision.FIRE if len(history) == 2 else Decision.CONTINUE, "t")

    history = [rec(n, 100) for n in range(1, 5)]
    assert replay_worker("w", frozenset({"c1"}), history, STALL1, decide).fired_after == 2
    assert seen == [1, 2]


@pytest.mark.parametrize("decision", [Decision.DONE, Decision.ESCALATE, Decision.RETRY])
def test_only_fire_fires(decision):
    history = [rec(1, 100), rec(2, 100)]

    def decide(checks, history, policy):
        return Verdict(decision, "t")

    assert replay_worker("w", frozenset({"c1"}), history, STALL1, decide).fired_after is None


RUN1 = worker_events(
    "a", {"c1", "c2"}, [(1_000, {"c1"}), (2_000, {"c1"}), (4_000, {"c1"})], run="r1"
)
RUN2 = worker_events(
    "b",
    {"c1", "c2", "c3"},
    [(1_000, {"c1"}), (1_000, {"c1", "c2"}), (1_000, {"c1", "c2"}), (1_000, {"c1", "c2", "c3"})],
    run="r2",
)


def test_aggregates_two_runs_under_two_policies():
    first, second = replay_runs([RUN1, RUN2], [STALL1, STALL2], decide=stall_decide)
    assert first == PolicyResult(STALL1, 2, 2, 1, 1, 5_000, 11_000)
    assert second == PolicyResult(STALL2, 2, 1, 0, 0, 0, 11_000)


def test_workers_without_check_results_are_skipped_including_their_cost():
    orphan = [
        ev("boss", EventType.HIRED, data={"worker": "z", "task": "t1"}),
        ev(
            "worker:z",
            EventType.SLICE_END,
            cost_micros=9_000,
            data={"slice": 1, "outcome": "completed", "status": {"status": "none"}},
        ),
    ]
    [result] = replay_runs([RUN1, orphan], [STALL1], decide=stall_decide)
    assert (result.workers, result.total_micros) == (1, 7_000)


def test_render_percentages_and_dollars_from_hand_worked_numbers():
    results = [
        PolicyResult(FiringPolicy(2, 6), 10, 4, 1, 1, 1_500_000, 6_000_000),
        PolicyResult(FiringPolicy(3, 8), 10, 3, 2, 0, 300_000, 3_000_000),
        PolicyResult(FiringPolicy(1, 4), 5, 0, 0, 0, 0, 0),
    ]
    lines = render_replay(results).splitlines()
    assert lines[0] == (
        "| stall | max slices | workers | fired | false firings | lost completions | saved |"
    )
    assert lines[2] == "| 2 | 6 | 10 | 4 | 1 (25.0%) | 1 | $1.5000 (25.0%) |"
    assert lines[3] == "| 3 | 8 | 10 | 3 | 2 (66.7%) | 0 | $0.3000 (10.0%) |"
    assert lines[4] == "| 1 | 4 | 5 | 0 | 0 (n/a) | 0 | $0.0000 (n/a) |"
    assert lines[-1] == (
        "False firings are workers the rule would have stopped that later passed a new check."
    )


def write_ledger(path: Path, events: list[Event]) -> None:
    with LedgerWriter(path) as w:
        for e in events:
            w.append(e)


def test_main_replays_every_ledger_under_the_folder(tmp_path, capsys):
    write_ledger(tmp_path / "a" / "ledger.jsonl", RUN1)
    write_ledger(tmp_path / "b" / "deep" / "ledger.jsonl", RUN2)
    argv = [str(tmp_path), "--stall", "1", "2", "--max-slices", "6"]
    assert main(argv, decide=stall_decide) == 0
    out = capsys.readouterr().out
    assert "| 1 | 6 | 2 | 2 | 1 (50.0%) | 1 | $0.0050 (45.5%) |" in out
    assert "| 2 | 6 | 2 | 1 | 0 (0.0%) | 0 | $0.0000 (0.0%) |" in out


def test_main_default_grid_is_three_by_three(tmp_path, capsys):
    write_ledger(tmp_path / "ledger.jsonl", RUN1)
    assert main([str(tmp_path)], decide=stall_decide) == 0
    assert len(capsys.readouterr().out.splitlines()) == 2 + 9 + 2


def test_main_fails_on_a_folder_without_slice_data(tmp_path, capsys):
    assert main([str(tmp_path)], decide=stall_decide) == 1
    assert "no ledger with slice data" in capsys.readouterr().err

    hired_only = [ev("boss", EventType.HIRED, data={"worker": "w", "task": "t1"})]
    write_ledger(tmp_path / "ledger.jsonl", hired_only)
    assert main([str(tmp_path)], decide=stall_decide) == 1


def test_main_rejects_a_nonpositive_policy_value(tmp_path):
    write_ledger(tmp_path / "ledger.jsonl", RUN1)
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--stall", "0"], decide=stall_decide)
    assert exc.value.code == 2
