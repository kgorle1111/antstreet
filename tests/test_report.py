import pytest

from boss.ledger import Billing, Event, EventType, total, totals_by
from boss.report import build_report, dollars, render_report


def ev(actor, event, round=1, **fields) -> Event:
    return Event(run="r1", round=round, actor=actor, event=event, **fields)


def check(check_id, status, detail="") -> Event:
    return ev(
        "gate", EventType.CHECK_RESULT, data={"check": check_id, "status": status, "detail": detail}
    )


def slice_end(worker, cost, outcome="completed", status="done", **tokens) -> Event:
    return ev(
        f"worker:{worker}",
        EventType.SLICE_END,
        cost_micros=cost,
        billing=Billing.SUBSCRIPTION,
        data={"outcome": outcome, "status": {"status": status, "reason": "because"}},
        **tokens,
    )


EVENTS = [
    ev("boss", EventType.BOSS_CALL, round=0, cost_micros=48_300, tokens_in=1200, tokens_out=900),
    ev("investor", EventType.APPROVED, round=0, data={"hashes": {}}),
    ev("boss", EventType.HIRED, data={"worker": "w1", "task": "t1", "model": "haiku"}),
    slice_end("w1", 5_896, tokens_in=1350, tokens_out=428, tokens_cached=10_738),
    check("c01", "failed", "pytest exited 1"),
    check("c02", "passed", "1 passed"),
    slice_end("w1", None, outcome="crashed", status="continuing"),
    check("c01", "passed", "1 passed"),
    ev("boss", EventType.ROUND_CLOSED, data={"passed": 2, "total": 2, "unlocked": True}),
]


def test_every_figure_equals_a_recomputation_from_the_ledger():
    report = build_report(EVENTS)
    assert report.total == total(EVENTS)
    assert report.by_actor == totals_by(EVENTS, lambda e: e.actor)
    assert sum(t.cost_micros for t in report.by_actor.values()) == report.total.cost_micros
    assert report.total.cost_micros == 48_300 + 5_896
    assert report.total.unknown_cost_events == 1
    assert report.by_actor["boss"].cost_micros == 48_300
    assert report.by_actor["worker:w1"].cost_micros == 5_896


def test_latest_check_result_wins():
    report = build_report(EVENTS)
    assert [(c.check, c.status) for c in report.checks] == [("c01", "passed"), ("c02", "passed")]


def test_worker_line_uses_the_last_slice():
    [w] = build_report(EVENTS).workers
    assert (w.worker, w.task, w.model, w.slices) == ("w1", "t1", "haiku", 2)
    assert (w.outcome, w.status, w.reason) == ("crashed", "continuing", "because")


def test_round_and_approval():
    report = build_report(EVENTS)
    assert report.approved
    [r] = report.rounds
    assert (r.n, r.passed, r.total, r.unlocked) == (1, 2, 2, True)
    assert not build_report(EVENTS[2:]).approved
    forged = ev("boss", EventType.APPROVED, round=0, data={"hashes": {}})
    assert not build_report([forged, *EVENTS[2:]]).approved


def test_rendered_text_labels_estimates_and_unknown_costs():
    text = render_report(build_report(EVENTS))
    assert "Spend (estimated by the CLI, not a bill)" in text
    assert "boss         $0.0483" in text
    assert "worker:w1    $0.0059 + 1 event(s) of unknown cost" in text
    assert "total        $0.0542 + 1 event(s) of unknown cost" in text
    assert "Round 1: 2/2 checks passed, next round unlocked" in text
    assert "c01  passed   1 passed" in text
    assert 'w1 on t1 (haiku): crashed, status continuing: "because", 2 slice(s)' in text


def test_notable_events_are_listed():
    events = [
        *EVENTS,
        ev("worker:w1", EventType.BLOCKED, data={"reason": "brief contradicts check c02"}),
        ev("boss", EventType.STOPPED, data={"reason": "worker did not start isolated"}),
    ]
    notes = build_report(events).notes
    assert notes == [
        "round 1: worker:w1 blocked (reason=brief contradicts check c02)",
        "round 1: boss stopped (reason=worker did not start isolated)",
    ]
    assert "Notes" in render_report(build_report(events))


def test_report_before_anything_ran():
    report = build_report([ev("investor", EventType.STOPPED, round=0, data={"reason": "rejected"})])
    text = render_report(report)
    assert "Approved by investor: NO" in text
    assert "No round has closed." in text
    assert "none run" in text and "none hired" in text
    assert "total        $0.0000" in text


def test_empty_or_mixed_ledgers_are_refused():
    with pytest.raises(ValueError, match="empty"):
        build_report([])
    other = Event(run="r2", round=0, actor="boss", event=EventType.STOPPED)
    with pytest.raises(ValueError, match="mixes runs"):
        build_report([EVENTS[0], other])


def test_dollars():
    assert dollars(5_896) == "$0.0059"
    assert dollars(1_250_000) == "$1.2500"
