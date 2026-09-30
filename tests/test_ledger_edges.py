"""Ledger edge cases: hostile or damaged files, writer lifecycle, and validation gaps."""

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
    base = {"run": "r1", "round": 1, "actor": "boss", "event": EventType.BOSS_CALL}
    return Event(**(base | overrides))


@pytest.fixture
def path(tmp_path):
    return tmp_path / "runs" / "ledger.jsonl"


def test_data_must_be_a_dict():
    with pytest.raises(ValueError, match="data must be a dict"):
        ev(data=["not", "a", "dict"])


def test_event_and_billing_accept_their_string_values_and_normalise_them():
    e = ev(event="hired", billing="api")
    assert e.event is EventType.HIRED
    assert e.billing is Billing.API


@pytest.mark.parametrize(
    "actor", ["worker:c01", "worker:A_b-9", "boss", "gate", "rule", "investor"]
)
def test_every_documented_actor_is_accepted(actor):
    assert ev(actor=actor).actor == actor


@pytest.mark.parametrize(
    "actor", ["worker:a b", "worker:a/b", "Boss", " boss", "worker:", "workers:a"]
)
def test_malformed_actors_are_rejected(actor):
    with pytest.raises(ValueError, match="unknown actor"):
        ev(actor=actor)


@pytest.mark.parametrize("actor", ["boss\n", "worker:c01\n"])
def test_actor_with_a_trailing_newline_is_rejected(actor):
    with pytest.raises(ValueError):
        ev(actor=actor)


def test_unknown_cost_survives_a_round_trip_and_is_not_zero(path):
    with LedgerWriter(path) as w:
        w.append(ev(cost_micros=None, data={"note": "unicode: café ✓"}))
    [back] = read_events(path)
    assert back.cost_micros is None
    assert back.data == {"note": "unicode: café ✓"}


def test_a_str_path_is_accepted_and_parent_folders_are_created(tmp_path):
    target = tmp_path / "a" / "b" / "ledger.jsonl"
    with LedgerWriter(str(target)) as w:  # type: ignore[arg-type]
        w.append(ev())
    assert len(read_events(target)) == 1


def test_reopening_appends_and_never_truncates(path):
    with LedgerWriter(path) as w:
        w.append(ev(round=1))
    with LedgerWriter(path) as w:
        w.append(ev(round=2))
    assert [e.round for e in read_events(path)] == [1, 2]


def test_an_event_is_durable_and_readable_before_the_writer_closes(path):
    with LedgerWriter(path) as w:
        w.append(ev())
        assert len(read_events(path)) == 1


def test_writer_lock_is_released_when_the_body_raises(path):
    with pytest.raises(RuntimeError), LedgerWriter(path) as w:
        w.append(ev())
        raise RuntimeError("boom")
    with LedgerWriter(path) as again:
        again.append(ev())
    assert len(read_events(path)) == 2


def test_second_writer_gets_a_locked_error_naming_the_file(path):
    with (
        LedgerWriter(path),
        pytest.raises(LedgerLockedError, match=r"ledger\.jsonl is held by another writer"),
    ):
        LedgerWriter(path).__enter__()


def test_leaving_a_writer_that_never_opened_is_harmless(path):
    writer = LedgerWriter(path)
    writer.__exit__(None, None, None)
    with pytest.raises(LedgerError, match="not open"):
        writer.append(ev())


def test_append_after_the_context_closed_is_refused(path):
    with LedgerWriter(path) as w:
        w.append(ev())
    with pytest.raises(LedgerError, match="not open"):
        w.append(ev())
    assert len(read_events(path)) == 1


def test_empty_file_reads_as_no_events(path):
    path.parent.mkdir(parents=True)
    path.write_text("")
    assert read_events(path) == []


def test_missing_file_is_an_os_error_not_an_empty_ledger(path):
    with pytest.raises(FileNotFoundError):
        read_events(path)


def test_blank_line_between_events_is_corruption_with_its_line_number(path):
    path.parent.mkdir(parents=True)
    line = ev().to_json()
    path.write_text(f"{line}\n\n{line}\n")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:2"):
        read_events(path)


def test_torn_final_line_is_corruption_with_its_line_number(path):
    path.parent.mkdir(parents=True)
    line = ev().to_json()
    path.write_text(f"{line}\n{line[: len(line) // 2]}")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:2"):
        read_events(path)


@pytest.mark.parametrize("line", ["[]", "null", '"text"', "7"])
def test_valid_json_that_is_not_an_object_is_corruption(path, line):
    path.parent.mkdir(parents=True)
    path.write_text(line + "\n")
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:1.*not a v1 ledger event"):
        read_events(path)


def test_event_without_a_version_is_corruption(path):
    record = json.loads(ev().to_json())
    del record["v"]
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(LedgerCorruptError, match="not a v1 ledger event"):
        read_events(path)


def test_wrong_typed_field_is_corruption_not_a_crash(path):
    record = json.loads(ev().to_json())
    record["cost_micros"] = "12"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record) + "\n")
    with pytest.raises(LedgerCorruptError, match="cost_micros"):
        read_events(path)


def test_totals_of_nothing_is_all_zero():
    assert total([]) == Totals()


def test_unknown_cost_events_are_counted_and_add_no_money():
    t = total([ev(cost_micros=5, tokens_in=1), ev(cost_micros=None, tokens_out=2, tokens_cached=3)])
    assert t == Totals(
        cost_micros=5, unknown_cost_events=1, tokens_in=1, tokens_out=2, tokens_cached=3, events=2
    )


def test_totals_by_groups_by_the_key_and_keeps_first_seen_order():
    events = [ev(actor="gate", cost_micros=2), ev(actor="boss", cost_micros=3), ev(cost_micros=4)]
    grouped = totals_by(events, lambda e: e.actor)
    assert list(grouped) == ["gate", "boss"]
    assert grouped["boss"].cost_micros == 7
    assert grouped["gate"].events == 1


def test_totals_by_accepts_a_one_shot_iterator():
    grouped = totals_by(iter([ev(round=1), ev(round=2), ev(round=1)]), lambda e: e.round)
    assert {k: v.events for k, v in grouped.items()} == {1: 2, 2: 1}
