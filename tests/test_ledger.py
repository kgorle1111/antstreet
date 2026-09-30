import json

import pytest

from boss.ledger import (
    Billing,
    Event,
    EventType,
    LedgerCorruptError,
    LedgerError,
    LedgerLockedError,
    LedgerWriter,
    Totals,
    read_events,
    total,
    totals_by,
)


def ev(**overrides) -> Event:
    base = {"run": "r1", "round": 1, "actor": "boss", "event": EventType.HIRED}
    return Event(**(base | overrides))


@pytest.fixture
def path(tmp_path):
    return tmp_path / "run" / "ledger.jsonl"


def write_all(path, events):
    with LedgerWriter(path) as w:
        for e in events:
            w.append(e)


def test_round_trip_preserves_every_field(path):
    original = [
        ev(),
        ev(
            actor="worker:w1",
            event=EventType.SLICE_END,
            cents_est=None,
            tokens_in=10,
            tokens_out=5,
            tokens_cached=100,
            billing=Billing.SUBSCRIPTION,
            data={"slice": 1, "status": "capped"},
        ),
    ]
    write_all(path, original)
    assert read_events(path) == original


def test_totals_equal_the_sum_of_events_and_keep_unknown_separate(path):
    events = [
        ev(actor="worker:a", event=EventType.SLICE_END, cents_est=120, tokens_in=7, tokens_out=3),
        ev(actor="worker:a", event=EventType.SLICE_END, cents_est=None, tokens_in=2),
        ev(actor="worker:b", round=2, event=EventType.SLICE_END, cents_est=30, tokens_cached=9),
        ev(actor="boss", event=EventType.APPROVED),
    ]
    write_all(path, events)
    got = total(read_events(path))
    assert got == Totals(
        cents_est=150, unknown_cost_events=1, tokens_in=9, tokens_out=3, tokens_cached=9, events=4
    )


def test_totals_by_actor_and_round(path):
    events = [
        ev(actor="worker:a", cents_est=100),
        ev(actor="worker:a", round=2, cents_est=50),
        ev(actor="worker:b", round=2, cents_est=5),
    ]
    by_actor = totals_by(events, lambda e: e.actor)
    by_round = totals_by(events, lambda e: e.round)
    assert {k: t.cents_est for k, t in by_actor.items()} == {"worker:a": 150, "worker:b": 5}
    assert {k: t.cents_est for k, t in by_round.items()} == {1: 100, 2: 55}
    assert sum(t.cents_est for t in by_actor.values()) == total(events).cents_est


def test_corrupt_line_raises_with_its_line_number(path):
    write_all(path, [ev(), ev()])
    with path.open("a") as fh:
        fh.write("{not json\n")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:3"):
        read_events(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("cents_est"),
        lambda d: d.update(extra=1),
        lambda d: d.update(v=99),
        lambda d: d.update(event="teleported"),
        lambda d: d.update(cents_est=-1),
    ],
    ids=["missing-field", "unknown-field", "wrong-version", "unknown-event", "negative-cents"],
)
def test_schema_violations_are_corruption(path, mutate):
    record = json.loads(ev().to_json())
    mutate(record)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(LedgerCorruptError):
        read_events(path)


def test_second_writer_is_refused_until_the_first_closes(path):
    with LedgerWriter(path) as first:
        first.append(ev())
        with pytest.raises(LedgerLockedError):
            LedgerWriter(path).__enter__()
    with LedgerWriter(path) as second:
        second.append(ev())
    assert len(read_events(path)) == 2


def test_append_outside_context_is_an_error(path):
    with pytest.raises(LedgerError):
        LedgerWriter(path).append(ev())


@pytest.mark.parametrize(
    "bad",
    [
        {"actor": "intern"},
        {"actor": "worker:"},
        {"cents_est": True},
        {"tokens_in": -3},
        {"round": 1.5},
        {"run": ""},
        {"billing": "free"},
    ],
    ids=str,
)
def test_invalid_events_are_rejected_before_anything_is_written(bad):
    with pytest.raises(ValueError):
        ev(**bad)


def test_unserialisable_data_leaves_the_file_untouched(path):
    write_all(path, [ev()])
    before = path.read_bytes()
    with LedgerWriter(path) as w, pytest.raises(TypeError):
        w.append(ev(data={"when": object()}))
    assert path.read_bytes() == before
