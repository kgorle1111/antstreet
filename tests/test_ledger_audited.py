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


# --- the key signs an audit verdict, so a line someone else adds or edits is not one ----------


@pytest.fixture
def run(tmp_path):
    from boss.rundir import RunPaths

    return RunPaths(tmp_path / "store" / ".boss" / "runs" / "r1")


def test_the_writer_signs_an_audited_event_and_a_reader_with_the_key_accepts_it(run):
    with run.writer() as ledger:
        ledger.append(ev("gate"))
    [event] = run.events()
    assert event.data["sig"].startswith("v2:")
    assert audited([event]) == [event]


def test_an_audited_line_added_without_the_key_is_refused_even_with_a_valid_chain(run):
    from boss.ledger import LedgerUnverifiedError

    with run.writer() as ledger:
        ledger.append(ev("gate"))
    with LedgerWriter(run.ledger) as keyless:  # chains correctly, signs nothing
        keyless.append(ev("gate"))
    assert len(read_events(run.ledger)) == 2  # a plain read cannot tell
    with pytest.raises(LedgerUnverifiedError, match="`audited` event by gate"):
        run.events()


def test_an_audited_verdict_edited_with_the_chain_recomputed_is_refused(run):
    import json

    from boss.ledger import GENESIS, LedgerUnverifiedError

    with run.writer() as ledger:
        ledger.append(ev("gate"))
    line = json.loads(run.ledger.read_text())
    line["data"]["verdict"] = "unrefuted"
    line["prev"] = GENESIS
    line.pop("mac")  # a forger has no key to sign the edited line with
    run.ledger.write_text(json.dumps(line, sort_keys=True) + "\n")
    with pytest.raises(LedgerUnverifiedError):
        run.events()
