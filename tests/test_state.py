from boss.errors import Outcome
from boss.ledger import Event, EventType
from boss.rule import SliceRecord
from boss.state import fired_workers, run_state, slice_history, worker_tasks


def ev(actor, event, **fields) -> Event:
    return Event(run="r1", round=1, actor=actor, event=event, **fields)


def slice_end(worker, n, cost, outcome="completed", status="continuing") -> Event:
    data = {"slice": n, "task": "t1", "outcome": outcome, "status": {"status": status}}
    return ev(f"worker:{worker}", EventType.SLICE_END, cost_micros=cost, data=data)


def check(worker, n, check_id, status) -> Event:
    data = {"check": check_id, "task": "t1", "status": status, "worker": worker, "slice": n}
    return ev("gate", EventType.CHECK_RESULT, data=data)


EVENTS = [
    ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "model": "haiku"}),
    slice_end("w1", 1, 5_000),
    check("w1", 1, "c01", "passed"),
    check("w1", 1, "c02", "failed"),
    slice_end("w1", 2, None, outcome="rate_limited"),
    slice_end("w1", 3, 7_000, status="done"),
    check("w1", 3, "c01", "passed"),
    check("w1", 3, "c02", "passed"),
    ev("boss", EventType.HIRED, data={"worker": "w2", "task": "t2", "model": "haiku"}),
    slice_end("w2", 1, 4_000, status="blocked"),
    check("w2", 1, "c03", "timeout"),
    ev("rule", EventType.FIRED, data={"worker": "w2", "task": "t2", "reason": "stalled"}),
]


def test_history_has_one_record_per_finished_slice_with_its_passing_checks():
    history = slice_history(EVENTS)
    assert history["w1"] == [
        SliceRecord(1, 5_000, Outcome.COMPLETED, "continuing", frozenset({"c01"})),
        SliceRecord(2, None, Outcome.RATE_LIMITED, "continuing", frozenset()),
        SliceRecord(3, 7_000, Outcome.COMPLETED, "done", frozenset({"c01", "c02"})),
    ]
    assert history["w2"] == [SliceRecord(1, 4_000, Outcome.COMPLETED, "blocked", frozenset())]


def test_check_results_without_a_worker_and_slice_are_ignored():
    untagged = ev("gate", EventType.CHECK_RESULT, data={"check": "c01", "status": "passed"})
    assert slice_history([slice_end("w1", 1, 1), untagged])["w1"][0].passing == frozenset()


def test_missing_status_is_none():
    event = ev("worker:w1", EventType.SLICE_END, data={"slice": 1, "outcome": "crashed"})
    [record] = slice_history([event])["w1"]
    assert (record.status, record.outcome) == ("none", Outcome.CRASHED)


def test_worker_tasks_and_fired_workers():
    assert worker_tasks(EVENTS) == {"w1": "t1", "w2": "t2"}
    assert fired_workers(EVENTS) == {"w2"}


def test_run_state_is_rebuilt_from_events_alone():
    events = [
        ev("investor", EventType.APPROVED, data={"hashes": {}}),
        *EVENTS,
        ev("boss", EventType.REASSIGNED, data={"task": "t2", "from": "w2", "to": "w3"}),
        ev("boss", EventType.HIRED, data={"worker": "w3", "task": "t2", "session": "s3"}),
        ev("boss", EventType.ABANDONED, data={"task": "t9", "reason": "blocked"}),
        ev("boss", EventType.ROUND_CLOSED, data={"passed": 2, "total": 3, "unlocked": True}),
        Event(run="r1", round=2, actor="investor", event=EventType.APPROVED, data={"round": 2}),
    ]
    state = run_state(events, ["t1", "t2", "t9"])
    assert state.tasks["t1"].workers == ("w1",)
    assert state.tasks["t1"].passing == frozenset({"c01", "c02"})
    assert state.tasks["t2"].workers == ("w2", "w3") and state.tasks["t2"].current == "w3"
    assert state.tasks["t2"].passing == frozenset()
    assert state.tasks["t9"].abandoned and state.tasks["t9"].current is None
    assert state.workers["w2"].fired and not state.workers["w1"].fired
    assert (state.workers["w1"].slices, state.workers["w3"].slices) == (3, 0)
    assert state.workers["w3"].session == "s3"
    assert state.closed_rounds == frozenset({1})
    assert state.approved_rounds == frozenset({1, 2})
    assert state.passing_total() == 2 and not state.stopped


def test_an_infrastructure_slice_does_not_wipe_out_what_passed_before_it():
    events = [
        ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "session": "s"}),
        slice_end("w1", 1, 5_000),
        check("w1", 1, "c01", "passed"),
        slice_end("w1", 2, None, outcome="rate_limited"),
    ]
    assert run_state(events, ["t1"]).tasks["t1"].passing == frozenset({"c01"})


def test_session_total_is_the_last_known_cumulative_figure():
    def end(n, total):
        data = {"slice": n, "outcome": "completed", "session_total_micros": total}
        return ev("worker:w1", EventType.SLICE_END, cost_micros=1, data=data)

    events = [
        ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "session": "s"}),
        end(1, 5_000),
        end(2, None),
        end(3, 12_000),
        end(4, None),
    ]
    assert run_state(events, ["t1"]).workers["w1"].session_total_micros == 12_000
    stopped = [*events, ev("boss", EventType.STOPPED, data={"reason": "x"})]
    assert run_state(stopped, ["t1"]).stopped
