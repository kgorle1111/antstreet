"""Run-level KPI counts: investor questions and the product verdict, read from a ledger."""

import pytest

from boss.kpi import (
    built,
    held_out_graded,
    investor_questions,
    product_verdict,
    single_said_done,
    span_seconds,
)
from boss.ledger import Event, EventType


def ev(actor: str, event: EventType, ts: str = "2026-10-02T10:00:00+00:00", **data) -> Event:
    return Event(run="r1", round=1, actor=actor, event=event, ts=ts, data=data)


def slice_end(status: str | None = "done") -> Event:
    data = {"outcome": "completed", "status": {"status": status} if status else {}}
    return Event(run="r1", round=1, actor="worker:w1", event=EventType.SLICE_END, data=data)


def product(check: str, status: str) -> Event:
    return ev("gate", EventType.CHECK_RESULT, check=check, status=status, scope="product")


# --- investor questions: one line of the counting rule per case ---------------------------------


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        (ev("investor", EventType.APPROVED, hashes={}), 1),  # the term sheet
        (ev("investor", EventType.APPROVED, round=2), 1),  # a later round's funding
        (ev("investor", EventType.APPROVED, round=3, added_checks=["c9"]), 1),  # the fix round
        (ev("investor", EventType.STOPPED, reason="term sheet rejected"), 1),
        (ev("investor", EventType.STOPPED, reason="round 2 not funded"), 1),
        (ev("investor", EventType.STOPPED, reason="interrupted before approval"), 0),
        (ev("rule", EventType.STOPPED, reason="round 2 not funded"), 0),  # not the investor's
        (ev("boss", EventType.STOPPED, reason="round 2 not funded"), 0),
        (ev("investor", EventType.RULED, ruling="dropped", check="c1"), 1),
        (ev("investor", EventType.RULED, ruling="unblocked", note="try x"), 1),
        (ev("investor", EventType.RULED, ruling="declined"), 1),
        (ev("boss", EventType.ABANDONED, task="t1", reason="disputed"), 1),
        (ev("boss", EventType.ABANDONED, task="t1", reason="blocked"), 1),
        (ev("boss", EventType.ABANDONED, task="t1", reason="refusal"), 1),
        (ev("boss", EventType.ABANDONED, task="t1", reason="already reassigned once"), 0),
        (ev("investor", EventType.RESUMED), 1),
        (ev("investor", EventType.TOPPED_UP, micros=100), 1),
        (ev("boss", EventType.APPROVED, hashes={}), 0),  # only the investor approves
        (
            ev("worker:w1", EventType.DISPUTED, check="c1", reason="wrong"),
            0,
        ),  # a claim, not a ruling
        (ev("boss", EventType.BOSS_CALL), 0),
    ],
)
def test_each_event_counts_as_the_rule_says(event, expected):
    assert investor_questions([event]) == expected


def test_a_ledger_with_known_questions_is_counted_exactly():
    events = [
        ev("boss", EventType.STARTED),
        ev("investor", EventType.APPROVED, hashes={}),  # 1 term sheet
        ev("boss", EventType.HIRED, worker="w1"),
        ev("worker:w1", EventType.DISPUTED, check="c1", reason="wrong"),
        ev("investor", EventType.RULED, ruling="dropped", check="c1"),  # 2
        ev("boss", EventType.ABANDONED, task="t2", reason="disputed"),  # 3 asked, set aside
        ev("boss", EventType.ABANDONED, task="t3", reason="already reassigned once"),  # no ask
        ev("investor", EventType.APPROVED, round=2),  # 4 round 2
        ev("investor", EventType.STOPPED, reason="round 3 not funded"),  # 5
        ev("investor", EventType.RESUMED),  # 6
        ev("investor", EventType.TOPPED_UP, micros=50),  # 7
        ev("boss", EventType.ROUND_CLOSED, passed=1, total=2, unlocked=False),
    ]
    assert investor_questions(events) == 7


def test_a_benchmark_runs_automatic_approvals_count_as_what_would_have_been_asked():
    # The harness answers `a` to every prompt: a disputed task is set aside, not ruled on.
    auto = [
        ev("investor", EventType.APPROVED, hashes={}),
        ev("boss", EventType.ABANDONED, task="t1", reason="disputed"),
        ev("boss", EventType.ABANDONED, task="t2", reason="blocked"),
    ]
    assert investor_questions(auto) == 3


def test_an_empty_ledger_asked_nothing():
    assert investor_questions([]) == 0


# --- product verdict ------------------------------------------------------------------------


def test_no_slice_means_no_verdict_and_nothing_built():
    events = [product("c1", "passed")]
    assert product_verdict(events) is None and not built(events)


def test_a_built_ledger_without_product_results_has_no_verdict():
    events = [slice_end()]
    assert built(events) and product_verdict(events) is None


def test_the_verdict_is_the_latest_product_result_of_each_check_after_the_last_slice():
    events = [
        slice_end(),
        product("c1", "failed"),  # before the last slice: superseded
        slice_end(),
        product("c1", "passed"),
        product("c2", "failed"),
        product("c2", "passed"),  # the later result wins
        product("c3", "failed"),
        ev("gate", EventType.CHECK_RESULT, check="c4", status="passed"),  # a worker's folder
        ev("gate", EventType.CHECK_RESULT, check="h1", status="passed", scope="held_out"),
    ]
    assert product_verdict(events) == (2, 3)


def test_held_out_results_keep_the_latest_per_check():
    events = [
        ev("gate", EventType.CHECK_RESULT, check="h1", status="failed", scope="held_out"),
        ev("gate", EventType.CHECK_RESULT, check="h1", status="passed", scope="held_out"),
        ev("gate", EventType.CHECK_RESULT, check="h2", status="failed", scope="held_out"),
        product("c1", "passed"),
    ]
    assert held_out_graded(events) == {"h1": True, "h2": False}


# --- the single arm's claim -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ([slice_end("done")], True),
        ([slice_end("blocked")], False),
        ([slice_end(None)], False),  # no status word at all
        ([], False),  # no slice ever ended
        ([slice_end("blocked"), slice_end("done")], True),  # the last slice speaks
        ([slice_end("done"), slice_end("blocked")], False),
    ],
)
def test_the_single_arm_said_done_only_by_its_last_status_word(events, expected):
    assert single_said_done(events) is expected


# --- time -----------------------------------------------------------------------------------


def test_the_span_is_first_to_last_event():
    events = [
        ev("boss", EventType.STARTED, ts="2026-10-02T10:00:00+00:00"),
        ev("boss", EventType.ROUND_CLOSED, ts="2026-10-02T10:01:30+00:00"),
        ev("boss", EventType.BOSS_CALL, ts="2026-10-02T10:00:10+00:00"),
    ]
    assert span_seconds(events) == 90.0


def test_one_event_or_none_has_no_span():
    assert span_seconds([]) is None
    assert span_seconds([ev("boss", EventType.STARTED)]) is None


def test_stamps_that_cannot_be_compared_give_no_span():
    events = [
        ev("boss", EventType.STARTED, ts="2026-10-02T10:00:00+00:00"),
        ev("boss", EventType.BOSS_CALL, ts="2026-10-02T10:00:05"),
    ]
    assert span_seconds(events) is None
