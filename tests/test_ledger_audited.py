"""`audited`: the gate's verdict on a change made outside a run. Only the gate's counts."""

import pytest

from boss.ledger import AUDIT_ACTOR, Event, EventType, LedgerWriter, audited, read_events

DATA = {"base": "a" * 40, "head": "b" * 40, "verdict": "refuted", "claim": "done"}


def ev(actor: str, kind: EventType = EventType.AUDITED) -> Event:
    return Event(run="r1", round=0, actor=actor, event=kind, data=DATA)


def test_the_type_exists_and_survives_a_round_trip():
    event = ev("gate")
    assert EventType("audited") is EventType.AUDITED
    assert Event.from_json(event.to_json()) == event


def test_only_the_gates_audited_events_count():
    events = [
        ev("gate"),
        ev("boss"),
        ev("investor"),
        ev("worker:w1"),
        ev("role:critic"),
        ev("rule"),
        ev("gate", EventType.CHECK_RESULT),
    ]
    assert audited(events) == [events[0]]
    assert AUDIT_ACTOR == "gate"


def test_a_forged_audited_line_is_a_valid_line_but_not_a_verdict(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with LedgerWriter(path) as ledger:
        ledger.append(ev("gate"))
        ledger.append(ev("worker:w1"))
    read = read_events(path)
    assert len(read) == 2
    assert [e.actor for e in audited(read)] == ["gate"]


@pytest.mark.parametrize("actor", ["gate\n", "Gate", "audit", ""])
def test_an_actor_that_is_not_one_of_the_known_forms_is_refused(actor):
    with pytest.raises(ValueError, match="unknown actor"):
        ev(actor)
