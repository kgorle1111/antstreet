"""B63: a resumed session's `modelUsage` is cumulative, so a slice books the difference in tokens
as it already does in cost. The figures come from the recorded stream fixtures."""

from pathlib import Path

import pytest

from boss.errors import Outcome
from boss.ledger import Event, EventType, total
from boss.rundir import slice_end_fields
from boss.runner import SliceRun
from boss.state import run_state
from boss.stream import StreamReader, Usage

FIXTURES = Path(__file__).parent / "fixtures"
ZERO = (0, 0, 0)


def fixture_run(name: str) -> SliceRun:
    reader = StreamReader()
    for line in (FIXTURES / name).read_text().splitlines():
        reader.feed(line)
    return SliceRun(Outcome.COMPLETED, reader.usage(), None, None, 0, 0.1, Path("x"))


def run_of(usage: Usage) -> SliceRun:
    return SliceRun(Outcome.COMPLETED, usage, None, None, 0, 0.1, Path("x"))


def end_event(fields: dict, worker: str = "w1") -> Event:
    return Event(
        run="r1",
        round=1,
        actor=f"worker:{worker}",
        event=EventType.SLICE_END,
        cost_micros=fields["cost_micros"],
        tokens_in=fields["tokens_in"],
        tokens_out=fields["tokens_out"],
        tokens_cached=fields["tokens_cached"],
        data=fields["data"],
    )


def start_event(n: int, session: str, worker: str = "w1") -> Event:
    data = {"slice": n, "task": "t1", "cap_micros": 1, "session": session}
    return Event(
        run="r1", round=1, actor=f"worker:{worker}", event=EventType.SLICE_START, data=data
    )


def worker_after(*events: Event):
    hired = Event(
        run="r1", round=1, actor="boss", event=EventType.HIRED, data={"worker": "w1", "task": "t1"}
    )
    return run_state([hired, *events], ["t1"]).workers["w1"]


def test_a_resumed_slice_books_only_its_own_tokens_the_fixtures_prove_it():
    capped = fixture_run("stream_budget_capped_2.1.285.jsonl")
    resumed = fixture_run("stream_resume_after_cap_2.1.285.jsonl")
    first = slice_end_fields(capped, 1, "t1", 0, ZERO)
    assert (first["tokens_in"], first["tokens_out"], first["tokens_cached"]) == (1499, 775, 10585)
    assert first["data"]["session_total_tokens"] == [1499, 775, 10585]

    state = worker_after(start_event(1, "s"), end_event(first))
    assert state.session_total_tokens == (1499, 775, 10585)

    second = slice_end_fields(
        resumed, 2, "t1", state.session_total_micros, state.session_total_tokens
    )
    # The resumed stream's own top-level `usage` is the slice alone: 42 + 3287 in, 2182 out,
    # 37769 cached. The booked figures must equal it.
    assert (second["tokens_in"], second["tokens_out"], second["tokens_cached"]) == (
        42 + 3287,
        2182,
        37769,
    )
    assert second["data"]["session_total_tokens"] == [4828, 2957, 48354]
    # Both slices together are the session's total, once.
    both = total([end_event(first), end_event(second)])
    assert (both.tokens_in, both.tokens_out, both.tokens_cached) == (4828, 2957, 48354)
    assert both.cost_micros == 29216


def test_without_the_previous_totals_the_resumed_slice_would_count_the_first_twice():
    # What the code did before: the proof that the previous totals are what removes the overlap.
    resumed = fixture_run("stream_resume_after_cap_2.1.285.jsonl")
    assert slice_end_fields(resumed, 2, "t1", 0, ZERO)["tokens_out"] == 2957


def test_a_total_below_the_previous_one_books_zero_not_a_negative():
    run = run_of(Usage(5, 10, 3, 4, cumulative=True))
    fields = slice_end_fields(run, 2, "t1", 0, (20, 1, 9))
    assert (fields["tokens_in"], fields["tokens_out"], fields["tokens_cached"]) == (0, 2, 0)


def test_a_slice_without_totals_books_its_own_message_tokens_and_reports_no_session_total():
    run = run_of(Usage(None, 110, 0, 7))  # killed: the sums of its own messages
    fields = slice_end_fields(run, 2, "t1", 5_000, (1_000, 500, 900))
    assert (fields["tokens_in"], fields["tokens_out"], fields["tokens_cached"]) == (110, 0, 7)
    assert fields["data"]["session_total_tokens"] is None
    assert fields["cost_micros"] is None


def test_tokens_a_killed_slice_booked_are_not_booked_again_by_the_next_total():
    first = slice_end_fields(run_of(Usage(1_000, 100, 40, 10, cumulative=True)), 1, "t1", 0, ZERO)
    killed = slice_end_fields(run_of(Usage(None, 30, 0, 5)), 2, "t1", 1_000, (100, 40, 10))
    state = worker_after(
        start_event(1, "s"), end_event(first), start_event(2, "s"), end_event(killed)
    )
    assert state.session_total_tokens == (130, 40, 15)  # the total covered by what is booked
    third = slice_end_fields(
        run_of(Usage(3_000, 250, 90, 40, cumulative=True)),
        3,
        "t1",
        1_000,
        state.session_total_tokens,
    )
    assert (third["tokens_in"], third["tokens_out"], third["tokens_cached"]) == (120, 50, 25)
    every = total([end_event(first), end_event(killed), end_event(third)])
    assert (every.tokens_in, every.tokens_out, every.tokens_cached) == (250, 90, 40)


def test_a_new_session_starts_its_token_total_from_zero():
    first = slice_end_fields(run_of(Usage(1_000, 100, 40, 10, cumulative=True)), 1, "t1", 0, ZERO)
    lost = slice_end_fields(run_of(Usage(None, 0, 0, 0)), 2, "t1", 1_000, (100, 40, 10))
    lost["data"]["outcome"] = "session_lost"
    state = worker_after(
        start_event(1, "a"),
        end_event(first),
        start_event(2, "a"),
        end_event(lost),
        start_event(3, "b"),  # a new attempt, a new session
    )
    assert (state.session, state.session_total_tokens) == (None, ZERO)


def test_ledgers_from_before_session_totals_carry_no_tokens():
    old = Event(
        run="r1",
        round=1,
        actor="worker:w1",
        event=EventType.SLICE_END,
        tokens_in=900,
        data={"slice": 1, "outcome": "completed", "session_total_micros": 3_000},
    )
    state = worker_after(start_event(1, "a"), old)
    assert (state.session, state.session_total_tokens) == ("a", ZERO)


@pytest.mark.parametrize("bad", [[1, 2], [1, 2, -3], [1, 2, 3.5], [True, 1, 1], "1,2,3", {"a": 1}])
def test_a_malformed_session_total_in_the_ledger_is_ignored_not_trusted(bad):
    fields = slice_end_fields(run_of(Usage(1_000, 100, 40, 10, cumulative=True)), 1, "t1", 0, ZERO)
    fields["data"]["session_total_tokens"] = bad
    state = worker_after(start_event(1, "a"), end_event(fields))
    # Read as a slice with no totals: only what the event itself booked is carried.
    assert state.session_total_tokens == (100, 40, 10)


def test_a_different_session_that_worked_never_inherits_the_previous_sessions_tokens():
    a = slice_end_fields(run_of(Usage(1_000, 100, 40, 10, cumulative=True)), 1, "t1", 0, ZERO)
    b = slice_end_fields(run_of(Usage(None, 7, 0, 1)), 2, "t1", 0, ZERO)  # b reported no totals
    b["data"]["session_total_micros"] = 500  # but proved itself with a cost total
    state = worker_after(start_event(1, "a"), end_event(a), start_event(2, "b"), end_event(b))
    assert (state.session, state.session_total_tokens) == ("b", (7, 0, 1))
