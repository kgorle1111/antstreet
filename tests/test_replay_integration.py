"""Replay recorded ledgers through the real `boss.rule.decide`.

test_bench_replay.py injects a fake `decide`; these tests check that replay and the real rule agree.
Ledgers are built from `Event`s following the data contract in `boss.state`, and every expected
number is worked by hand in a comment next to its fixture.
"""

from pathlib import Path

from boss.bench.replay import (
    PolicyResult,
    WorkerReplay,
    main,
    replay_runs,
    replay_worker,
    task_checks_by_worker,
)
from boss.errors import INFRASTRUCTURE, Outcome
from boss.ledger import Event, EventType, LedgerWriter
from boss.rule import FiringPolicy, decide
from boss.state import slice_history

OK = Outcome.COMPLETED
RATE = Outcome.RATE_LIMITED


def ledger(
    worker: str, checks: list[str], slices: list[tuple[int, Outcome, set[str]]], run: str = "r1"
) -> list[Event]:
    """Events as the live loop records them. Each slice is (cost_micros, outcome, checks passing
    after it). Infrastructure slices get no check_result events: the gate does not run after them.
    """
    events = [Event(run=run, round=1, actor="boss", event=EventType.HIRED, data={"worker": worker})]
    for n, (cost, outcome, passing) in enumerate(slices, start=1):
        end = {"slice": n, "task": "t1", "outcome": outcome.value, "status": {"status": "none"}}
        events.append(
            Event(
                run=run,
                round=1,
                actor=f"worker:{worker}",
                event=EventType.SLICE_END,
                cost_micros=cost,
                data=end,
            )
        )
        if outcome in INFRASTRUCTURE:
            continue
        for c in checks:
            data = {"check": c, "task": "t1", "worker": worker, "slice": n}
            data["status"] = "passed" if c in passing else "failed"
            events.append(
                Event(run=run, round=1, actor="gate", event=EventType.CHECK_RESULT, data=data)
            )
    return events


def replay_one(events: list[Event], stall: int = 2, max_slices: int = 6) -> WorkerReplay:
    """The single worker's replay under one policy with the real rule."""
    [(worker, history)] = slice_history(events).items()
    checks = task_checks_by_worker(events)[worker]
    return replay_worker(worker, checks, history, FiringPolicy(stall, max_slices), decide)


# --- Fixtures shared by the per-worker tests and the aggregate tests -----------------------------

# W_PROG: 5 checks; slice n passes c1..cn for n = 1..4. Every slice adds a check, so stalled is
# always 0 and no check set is complete: never fired by any policy with max_slices >= 5.
W_PROG = ledger(
    "prog",
    ["c1", "c2", "c3", "c4", "c5"],
    [
        (1_000, OK, {"c1"}),
        (1_000, OK, {"c1", "c2"}),
        (1_000, OK, {"c1", "c2", "c3"}),
        (1_000, OK, {"c1", "c2", "c3", "c4"}),
    ],
)

# W_FALSE: 3 checks; slices [progress, stall, stall, progress]: c1 | c1 | c1 | c1 c2.
# stalled after each slice: 0, 1, 2, 0.
W_FALSE = ledger(
    "false",
    ["c1", "c2", "c3"],
    [(1_000, OK, {"c1"}), (2_000, OK, {"c1"}), (3_000, OK, {"c1"}), (4_000, OK, {"c1", "c2"})],
)

# W_LOST: same shape as W_FALSE but only 2 checks, so slice 4 (c1 c2) completes the task.
W_LOST = ledger(
    "lost",
    ["c1", "c2"],
    [(600, OK, {"c1"}), (600, OK, {"c1"}), (600, OK, {"c1"}), (600, OK, {"c1", "c2"})],
)


def test_a_worker_that_passes_one_more_check_every_slice_is_never_fired():
    got = replay_one(W_PROG, stall=2, max_slices=6)
    assert got == WorkerReplay("prog", 4, None, 0, False, False)


def test_progress_stall_stall_progress_is_fired_after_slice_3_as_a_false_firing():
    # stall=2: stalled is 0,1,2 after slices 1..3, so FIRE after slice 3. Slice 4 adds c2, a check
    # no earlier slice passed => false firing. It never completes (c3 missing) => not lost.
    # saved = slice 4's cost = 4_000.
    got = replay_one(W_FALSE, stall=2)
    assert got == WorkerReplay("false", 4, 3, 4_000, True, False)


def test_a_worker_that_recovers_in_time_is_not_fired_under_a_looser_stall():
    # stall=3: stalled peaks at 2 (after slice 3) and slice 4 resets it to 0.
    assert replay_one(W_FALSE, stall=3).fired_after is None


def test_stalling_twice_then_completing_every_check_is_a_lost_completion():
    # stall=2: FIRE after slice 3; slice 4 passes c1 and c2 = all checks => lost completion.
    # saved = 600. False firing too: c2 is new after the firing point.
    got = replay_one(W_LOST, stall=2)
    assert got == WorkerReplay("lost", 4, 3, 600, True, True)
    # stall=3: the rule reaches slice 4 with all checks passing and says DONE, not FIRE.
    assert replay_one(W_LOST, stall=3).fired_after is None


def test_infrastructure_slices_between_counted_slices_do_not_advance_the_stall_count():
    # Slices: 1 ok c1 | 2 rate_limited | 3 rate_limited | 4 ok c1 | 5 ok c1 | 6 ok c1.
    # Counted slices only: 1, 4, 5, 6. Stalled after each counted slice: 0, 1, 2, 3.
    # stall=2 fires after slice 5 (2nd counted stall). If infrastructure slices were counted it
    # would fire after slice 3. Slice 6 is saved: 6_000.
    events = ledger(
        "infra",
        ["c1", "c2"],
        [
            (1_000, OK, {"c1"}),
            (1_000, RATE, set()),
            (1_000, RATE, set()),
            (1_000, OK, {"c1"}),
            (1_000, OK, {"c1"}),
            (6_000, OK, {"c1"}),
        ],
    )
    assert replay_one(events, stall=2) == WorkerReplay("infra", 6, 5, 6_000, False, False)
    # Same history under max_slices=3: counted slices reach 3 at slice 5 (1, 4, 5), not slice 3.
    assert replay_one(events, stall=9, max_slices=3).fired_after == 5


def test_hitting_max_slices_while_still_progressing_fires_and_counts_later_slices_as_saved():
    # 9 checks, slice n passes c1..cn for n = 1..8, cost n * 1_000. max_slices=6: counted reaches 6
    # after slice 6 => FIRE "slice limit" (stalled is 0 throughout). Slices 7 and 8 are saved:
    # 7_000 + 8_000 = 15_000. They add c7 and c8, new checks => false firing; c9 never passes =>
    # not lost.
    checks = [f"c{i}" for i in range(1, 10)]
    slices = [(n * 1_000, OK, {f"c{i}" for i in range(1, n + 1)}) for n in range(1, 9)]
    got = replay_one(ledger("limit", checks, slices), stall=2, max_slices=6)
    assert got == WorkerReplay("limit", 8, 6, 15_000, True, False)
    # One slice earlier it would still be running.
    assert (
        replay_one(ledger("limit", checks, slices[:5]), stall=2, max_slices=6).fired_after is None
    )


# --- Aggregation ----------------------------------------------------------------------------------

RUNS = [W_PROG + W_FALSE, W_LOST]
# Ledger 1 holds W_PROG and W_FALSE (their events do not interleave; worker names are distinct).
# total_micros = PROG 4 x 1_000 + FALSE (1+2+3+4) x 1_000 + LOST 4 x 600 = 4_000 + 10_000 + 2_400
#              = 16_400 for every policy.
#
# stall=1, max=6:  PROG never fires.  FALSE fires after slice 2 (stalled 1), saves 3_000 + 4_000
#                  = 7_000, false firing (c2 later), not lost.  LOST fires after slice 2, saves
#                  600 + 600 = 1_200, false firing, lost (slice 4 completes).
#                  => workers 3, fired 2, false 2, lost 1, saved 8_200.
# stall=2, max=6:  FALSE fires after 3, saves 4_000, false.  LOST fires after 3, saves 600, false,
#                  lost.  => 3, 2, 2, 1, saved 4_600.
# stall=3, max=6:  FALSE recovers at slice 4, LOST is DONE at slice 4, PROG progresses.
#                  => 3, 0, 0, 0, saved 0.
P1, P2, P3 = (FiringPolicy(s, 6) for s in (1, 2, 3))
HAND_WORKED = [
    PolicyResult(P1, 3, 2, 2, 1, 8_200, 16_400),
    PolicyResult(P2, 3, 2, 2, 1, 4_600, 16_400),
    PolicyResult(P3, 3, 0, 0, 0, 0, 16_400),
]


def test_two_ledgers_and_three_policies_give_the_hand_worked_totals():
    assert replay_runs(RUNS, [P1, P2, P3]) == HAND_WORKED


def test_tightening_stall_slices_never_decreases_the_number_fired():
    stalls = [4, 3, 2, 1]  # loosest to tightest
    for max_slices in (3, 4, 6, 8):
        fired = [r.fired for r in replay_runs(RUNS, [FiringPolicy(s, max_slices) for s in stalls])]
        assert fired == sorted(fired), (max_slices, fired)
    for stall in (1, 2, 3):  # the same holds for tightening max_slices
        fired = [r.fired for r in replay_runs(RUNS, [FiringPolicy(stall, m) for m in (8, 6, 4, 2)])]
        assert fired == sorted(fired), (stall, fired)


def test_main_prints_the_hand_worked_table_from_ledgers_on_disk(tmp_path: Path, capsys):
    for name, events in (("a", W_PROG + W_FALSE), ("b/deep", W_LOST)):
        path = tmp_path / name / "ledger.jsonl"
        with LedgerWriter(path) as writer:
            for e in events:
                writer.append(e)

    assert main([str(tmp_path), "--stall", "1", "2", "3", "--max-slices", "6"]) == 0

    # Shares: false 2/2 = 100.0%; saved 8_200/16_400 = 50.0%, 4_600/16_400 = 28.05% -> 28.0%.
    # Dollars: 8_200 micros = $0.0082, 4_600 micros = $0.0046. stall=3 fired nothing: 0/0 = n/a.
    lines = capsys.readouterr().out.splitlines()
    assert lines[2:5] == [
        "| 1 | 6 | 3 | 2 | 2 (100.0%) | 1 | $0.0082 (50.0%) |",
        "| 2 | 6 | 3 | 2 | 2 (100.0%) | 1 | $0.0046 (28.0%) |",
        "| 3 | 6 | 3 | 0 | 0 (n/a) | 0 | $0.0000 (0.0%) |",
    ]
