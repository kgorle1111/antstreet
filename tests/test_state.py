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
    assert state.tasks["t2"].passing == frozenset() and state.tasks["t2"].best == "w3"
    assert state.tasks["t1"].best == "w1"
    assert state.tasks["t9"].abandoned and state.tasks["t9"].current is None
    assert state.workers["w2"].fired and not state.workers["w1"].fired
    assert (state.workers["w1"].slices, state.workers["w3"].slices) == (3, 0)
    assert state.workers["w3"].session is None  # no slice has proved the session exists
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


def test_a_replacement_that_never_ran_does_not_discard_its_predecessors_passing_checks():
    events = [
        ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "session": "a"}),
        slice_end("w1", 1, 5_000),
        check("w1", 1, "c01", "passed"),
        check("w1", 1, "c02", "failed"),
        ev("rule", EventType.FIRED, data={"worker": "w1", "task": "t1", "reason": "no progress"}),
        ev("boss", EventType.HIRED, data={"worker": "w2", "task": "t1", "session": "b"}),
    ]
    task = run_state(events, ["t1"]).tasks["t1"]
    assert (task.current, task.best, task.passing) == ("w2", "w1", frozenset({"c01"}))
    better = [
        *events,
        slice_end("w2", 1, 5_000),
        check("w2", 1, "c01", "passed"),
        check("w2", 1, "c02", "passed"),
    ]
    task = run_state(better, ["t1"]).tasks["t1"]
    assert (task.best, task.passing) == ("w2", frozenset({"c01", "c02"}))


def test_disputes_are_attached_to_the_slice_they_were_raised_in():
    def dispute(actor, check_id, **placed) -> Event:
        data = {"task": "t1", "check": check_id, "reason": "contradicts the idea"} | placed
        return ev(f"worker:{actor}", EventType.DISPUTED, data=data)

    events = [
        *EVENTS,
        dispute("w1", "c02", worker="w1", slice=1),
        dispute("w1", "c09", worker="w1", slice=3),
        dispute("w2", "c03", worker="w2", slice=1),
        dispute("w1", "c05"),  # no worker or slice: cannot be placed, so it is ignored
    ]
    history = slice_history(events)
    assert [r.disputed for r in history["w1"]] == [{"c02"}, frozenset(), {"c09"}]
    assert [r.disputed for r in history["w2"]] == [{"c03"}]
    assert all(r.disputed == frozenset() for r in slice_history(EVENTS)["w1"])


def start(worker, n, session=None) -> Event:
    data = {"slice": n, "task": "t1", "cap_micros": 1} | ({"session": session} if session else {})
    return ev(f"worker:{worker}", EventType.SLICE_START, data=data)


def ended(worker, n, total, outcome="completed") -> Event:
    data = {"slice": n, "outcome": outcome, "session_total_micros": total}
    return ev(f"worker:{worker}", EventType.SLICE_END, cost_micros=1, data=data)


def worker_of(*events):
    hired = ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1"})
    return run_state([hired, *events], ["t1"]).workers["w1"]


def test_a_session_is_resumable_only_after_a_slice_in_it_got_past_infrastructure():
    assert worker_of().session is None
    assert worker_of(start("w1", 1, "a")).session is None  # interrupted: it may not exist
    assert worker_of(start("w1", 1, "a"), ended("w1", 1, None, "rate_limited")).session is None
    failed = worker_of(start("w1", 1, "a"), ended("w1", 1, 7_000, "api_error"))
    assert (failed.session, failed.session_total_micros) == (None, 0)  # its total is not carried
    done = worker_of(start("w1", 1, "a"), ended("w1", 1, 5_000))
    assert (done.session, done.session_total_micros) == ("a", 5_000)


def test_the_live_session_is_the_last_one_that_worked_and_its_total_is_its_own():
    w = worker_of(
        start("w1", 1, "a"),
        ended("w1", 1, None, "api_error"),
        start("w1", 1, "b"),  # a new attempt, a new session
        ended("w1", 1, 4_000),
        start("w1", 2, "b"),
        ended("w1", 2, 9_000),
        start("w1", 3, "b"),
        ended("w1", 3, None, "rate_limited"),  # a failed resume does not lose the session
        start("w1", 4, "b"),  # interrupted resume
    )
    assert (w.session, w.session_total_micros, w.slices) == ("b", 9_000, 4)


def test_a_total_reported_by_an_abandoned_session_is_not_carried_into_the_next():
    w = worker_of(
        start("w1", 1, "a"),
        ended("w1", 1, 7_000, "api_error"),  # spent, then failed: session a is not resumed
        start("w1", 1, "b"),
        ended("w1", 1, 2_000),
    )
    assert (w.session, w.session_total_micros) == ("b", 2_000)


def test_ledgers_from_before_per_slice_sessions_fall_back_to_the_hired_session():
    hired = ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "session": "old"})
    events = [hired, start("w1", 1), ended("w1", 1, 3_000)]
    w = run_state(events, ["t1"]).workers["w1"]
    assert (w.session, w.session_total_micros) == ("old", 3_000)


def test_a_stop_holds_until_the_investor_resumes_and_a_later_stop_holds_again():
    hired = ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1"})
    stop = ev("boss", EventType.STOPPED, data={"reason": "x"})
    by_boss = ev("boss", EventType.RESUMED)
    by_investor = ev("investor", EventType.RESUMED)
    assert run_state([hired, stop], ["t1"]).stopped
    assert run_state([hired, stop, by_boss], ["t1"]).stopped
    assert not run_state([hired, stop, by_investor], ["t1"]).stopped
    assert run_state([hired, stop, by_investor, stop], ["t1"]).stopped
    assert not run_state([hired, by_investor], ["t1"]).stopped


def test_locked_rounds_are_the_ones_that_closed_below_their_threshold():
    def closed(n, unlocked):
        data = {"passed": 1, "total": 2, "unlocked": unlocked}
        return Event(run="r1", round=n, actor="boss", event=EventType.ROUND_CLOSED, data=data)

    state = run_state([closed(1, True), closed(2, False)], [])
    assert state.closed_rounds == {1, 2} and state.locked_rounds == {2}
    malformed = Event(run="r1", round=3, actor="boss", event=EventType.ROUND_CLOSED)
    assert run_state([malformed], []).locked_rounds == {3}  # no proof it unlocked: locked


def test_a_dropped_check_counts_for_nothing_and_a_ruled_dispute_is_settled():
    def ruled_event(kind, check_id, actor="investor") -> Event:
        data = {"task": "t1", "worker": "w1", "check": check_id, "ruling": kind}
        return ev(actor, EventType.RULED, data=data)

    def dispute_event(check_id) -> Event:
        data = {"task": "t1", "check": check_id, "reason": "r", "worker": "w1", "slice": 1}
        return ev("worker:w1", EventType.DISPUTED, data=data)

    base = [
        ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1"}),
        slice_end("w1", 1, 5_000),
        check("w1", 1, "c01", "passed"),
        check("w1", 1, "c02", "passed"),
        dispute_event("c03"),
        dispute_event("c04"),
        dispute_event("c05"),
    ]
    before = run_state(base, ["t1"])
    assert before.dropped == frozenset() and before.tasks["t1"].passing == {"c01", "c02"}
    assert slice_history(base)["w1"][0].disputed == {"c03", "c04", "c05"}

    events = [
        *base,
        ruled_event("dropped", "c02"),
        ruled_event("kept", "c03"),
        ruled_event("dropped", "c04", actor="worker:w1"),  # not the investor: no effect
    ]
    after = run_state(events, ["t1"])
    assert after.dropped == {"c02"}
    assert after.tasks["t1"].passing == {"c01"} and after.passing_total() == 1
    [record] = slice_history(events)["w1"]
    assert record.passing == {"c01"} and record.disputed == {"c04", "c05"}


def test_a_slice_that_crashed_without_reporting_does_not_prove_its_session_exists():
    crashed = worker_of(start("w1", 1, "a"), ended("w1", 1, None, "crashed"))
    assert (crashed.session, crashed.session_total_micros) == (None, 0)
    timed_out = worker_of(start("w1", 1, "a"), ended("w1", 1, None, "timeout"))
    assert timed_out.session is None
    reported = worker_of(start("w1", 1, "a"), ended("w1", 1, 0, "capped"))
    assert (reported.session, reported.session_total_micros) == ("a", 0)
