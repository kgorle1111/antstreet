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
            cost_micros=None,
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
        ev(actor="worker:a", event=EventType.SLICE_END, cost_micros=120, tokens_in=7, tokens_out=3),
        ev(actor="worker:a", event=EventType.SLICE_END, cost_micros=None, tokens_in=2),
        ev(actor="worker:b", round=2, event=EventType.SLICE_END, cost_micros=30, tokens_cached=9),
        ev(actor="boss", event=EventType.APPROVED),
    ]
    write_all(path, events)
    got = total(read_events(path))
    assert got == Totals(
        cost_micros=150, unknown_cost_events=1, tokens_in=9, tokens_out=3, tokens_cached=9, events=4
    )


def test_totals_by_actor_and_round(path):
    events = [
        ev(actor="worker:a", cost_micros=100),
        ev(actor="worker:a", round=2, cost_micros=50),
        ev(actor="worker:b", round=2, cost_micros=5),
    ]
    by_actor = totals_by(events, lambda e: e.actor)
    by_round = totals_by(events, lambda e: e.round)
    assert {k: t.cost_micros for k, t in by_actor.items()} == {"worker:a": 150, "worker:b": 5}
    assert {k: t.cost_micros for k, t in by_round.items()} == {1: 100, 2: 55}
    assert sum(t.cost_micros for t in by_actor.values()) == total(events).cost_micros


def test_corrupt_line_raises_with_its_line_number(path):
    write_all(path, [ev(), ev()])
    with path.open("a") as fh:
        fh.write("{not json\n")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:3"):
        read_events(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("cost_micros"),
        lambda d: d.update(extra=1),
        lambda d: d.update(v=99),
        lambda d: d.update(event="teleported"),
        lambda d: d.update(cost_micros=-1),
    ],
    ids=["missing-field", "unknown-field", "wrong-version", "unknown-event", "negative-cost"],
)
def test_schema_violations_are_corruption(path, mutate):
    record = json.loads(ev().to_json())
    mutate(record)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(LedgerCorruptError):
        read_events(path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("run", 5),
        ("run", ""),
        ("run", None),
        ("actor", 5),
        ("actor", ""),
        ("actor", "boss\n"),
        ("ts", None),
        ("ts", 5),
        ("ts", ""),
        ("ts", "yesterday"),
    ],
    ids=str,
)
def test_run_actor_and_ts_of_the_wrong_kind_are_corruption_with_a_line_number(path, key, value):
    record = json.loads(ev().to_json())
    record[key] = value
    write_all(path, [ev()])
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:2"):
        read_events(path)


@pytest.mark.parametrize("bad", [{"run": 5}, {"actor": 5}, {"ts": None}, {"ts": "not a time"}])
def test_event_rejects_run_actor_or_ts_of_the_wrong_kind(bad):
    with pytest.raises(ValueError):
        ev(**bad)


def test_a_deeply_nested_line_is_corruption(path):
    write_all(path, [ev()])
    with path.open("a") as fh:
        fh.write("[" * 100_000 + "\n")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:2"):
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
        {"cost_micros": True},
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


def test_every_event_with_an_unknown_cost_is_counted() -> None:
    t = total([ev(cost_micros=None), ev(cost_micros=None), ev(cost_micros=7)])
    assert (t.unknown_cost_events, t.cost_micros) == (2, 7)


def test_the_default_timestamp_is_utc() -> None:
    from datetime import UTC, datetime

    assert datetime.fromisoformat(ev().ts).utcoffset() == UTC.utcoffset(None)


def test_a_line_is_written_with_its_keys_in_sorted_order() -> None:
    keys = list(json.loads(ev(data={"b": 1, "a": 2}).to_json()))
    assert keys == sorted(keys)
    assert list(json.loads(ev(data={"b": 1, "a": 2}).to_json())["data"]) == ["a", "b"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"run": 5}, "run must be a string"),
        ({"run": ""}, "run must be non-empty"),
        ({"round": -1}, "round must be a non-negative int"),
        ({"tokens_in": -1}, "tokens_in must be a non-negative int"),
        ({"tokens_cached": True}, "tokens_cached must be a non-negative int"),
        ({"prev": "xyz"}, "prev must be 64 lower-case hex digits"),
    ],
)
def test_an_invalid_event_says_which_field_and_why(overrides, message) -> None:
    with pytest.raises(ValueError, match=message):
        ev(**overrides)


def test_a_line_that_cannot_be_read_says_why() -> None:
    good = json.loads(ev().to_json())
    with pytest.raises(ValueError, match="nested too deeply"):
        Event.from_json("[" * 100_000)
    with pytest.raises(ValueError, match="prev must be a string"):
        Event.from_json(json.dumps(good | {"prev": None}))
    with pytest.raises(ValueError, match=r"fields differ from schema: \['zzz'\]"):
        Event.from_json(json.dumps(good | {"zzz": 1}))
    del good["cost_micros"]
    with pytest.raises(ValueError, match=r"fields differ from schema: \['cost_micros'\]"):
        Event.from_json(json.dumps(good))


def test_a_ledger_whose_last_line_lost_its_newline_can_be_appended_to_after_several_lines(
    path,
) -> None:
    write_all(path, [ev(), ev(), ev()])
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))
    write_all(path, [ev()])
    assert len(read_events(path)) == 4
