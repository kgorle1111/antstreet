"""Every investor event is signed, and every reader that trusts one refuses a forgery (T46).

The claim under test: an actor that can write the ledger and recompute its hash chain but cannot
read `<project>/.boss/investor.key` cannot make a `ruled`, `resumed`, `topped_up`, `stopped` or
round-`approved` event that any reader acts on. The writer signs; `read_events(path, key_path)`
refuses the ledger otherwise, so the pure functions that act on events (`rulings.ruled`,
`budget.round_budget`, `state.run_state`, the pipeline's `_settled`) never see a forgery.
"""

# ruff: noqa: F401, F811  (`boss` is a fixture imported from test_cli)
import dataclasses
import random

import pytest
from test_cli import boss, events_of_run, locked_run, slices_started

from boss import budget, pipeline, rulings, signing
from boss.cli import EXIT_FAILED, EXIT_INCOMPLETE, EXIT_OK
from boss.ledger import GENESIS, Event, EventType, LedgerUnverifiedError, LedgerWriter, read_events
from boss.rundir import RunPaths
from boss.signing import SigningError, load_key
from boss.state import run_state
from boss.termsheet import CheckSpec, Round, Task, TermSheet

SHEET = TermSheet(
    idea="Reverse a string.",
    budget_micros=500_000,
    rounds=(Round(1, 300_000, 1), Round(2, 200_000, 1)),
    checks=(CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
    tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
)
# One of every investor event the code writes, with the data it writes.
TASK = {"task": "t1", "worker": "w1"}
AMENDMENT = {"hashes": {"term_sheet": "ab"}, "round": 2, "added_checks": ["c02"]}
INVESTOR = {
    "ruled-dropped": (EventType.RULED, 1, TASK | {"check": "c01", "ruling": "dropped"}),
    "ruled-kept": (EventType.RULED, 1, TASK | {"check": "c01", "ruling": "kept"}),
    "ruled-unblocked": (EventType.RULED, 1, TASK | {"ruling": "unblocked", "note": "go"}),
    "ruled-declined": (EventType.RULED, 0, {"ruling": "declined"}),
    "resumed": (EventType.RESUMED, 1, {}),
    "topped_up": (EventType.TOPPED_UP, 1, {"micros": 200_000}),
    "stopped": (EventType.STOPPED, 1, {"reason": "round 1 not funded"}),
    "round-approved": (EventType.APPROVED, 2, {"round": 2}),
    "amendment-approved": (EventType.APPROVED, 2, AMENDMENT),
}


@pytest.fixture
def run(tmp_path):
    return RunPaths(tmp_path / "project" / ".boss" / "runs" / "r1")


def investor(name: str) -> Event:
    kind, round_, data = INVESTOR[name]
    return Event(run="r1", round=round_, actor="investor", event=kind, data=data)


def boss_call(cost: int = 4_000) -> Event:
    return Event(run="r1", round=0, actor="boss", event=EventType.BOSS_CALL, cost_micros=cost)


def honest(run: RunPaths, *events: Event) -> list[Event]:
    """What the real writer makes of these events, with the key."""
    with run.writer() as ledger:
        for event in events:
            ledger.append(event)
    return run.events()


def attacker(run: RunPaths, *events: Event) -> None:
    """A writer with no key rewrites the whole file: every `prev` is valid again."""
    run.ledger.unlink(missing_ok=True)
    with LedgerWriter(run.ledger) as ledger:
        for event in events:
            ledger.append(event)


def forgery_of(name: str, how: str, genuine: Event | None = None) -> Event:
    event = investor(name)
    sig = {"none": None, "made-up": "v2:" + "0" * 64, "first-form": "0" * 64}.get(how)
    if how == "copied" and genuine is not None:
        sig = genuine.data[signing.SIG_KEY]
    return event if sig is None else dataclasses.replace(event, data={**event.data, "sig": sig})


# --- the writer signs every investor event, and only those ------------------------------------


@pytest.mark.parametrize("name", INVESTOR)
def test_the_writer_signs_every_investor_event_and_reads_it_back(run, name):
    events = honest(run, boss_call(), investor(name))
    first, second = events
    key = load_key(run.investor_key)
    assert "sig" not in first.data  # the boss's own lines carry no signature
    assert second.data["sig"].startswith("v2:") and signing.verify(key, second)
    assert {k: v for k, v in second.data.items() if k != "sig"} == INVESTOR[name][2]


@pytest.mark.parametrize("actor", ["boss", "gate", "rule", "worker:w1", "role:critic"])
def test_nobody_but_the_investor_is_signed_for(run, actor):
    event = Event(run="r1", round=1, actor=actor, event=EventType.STOPPED, data={"reason": "x"})
    [only] = honest(run, event)
    assert only.data == {"reason": "x"}


def test_a_writer_without_a_key_path_writes_what_it_always_did(tmp_path):
    path = tmp_path / "ledger.jsonl"
    with LedgerWriter(path) as ledger:
        ledger.append(investor("resumed"))
    assert read_events(path)[0].data == {}


def test_a_key_that_cannot_be_used_stops_the_writer_opening(run):
    honest(run, boss_call(), investor("resumed"))
    before = run.ledger.read_bytes()
    run.investor_key.chmod(0o644)
    with pytest.raises(LedgerUnverifiedError, match="chmod 600"), run.writer():
        pytest.fail("a ledger is not opened for append when the key cannot be used")
    assert run.ledger.read_bytes() == before


def test_a_key_that_breaks_mid_run_signs_nothing_false_and_loses_no_other_record(run):
    with run.writer() as ledger:
        ledger.append(boss_call())
        ledger.append(investor("resumed"))  # creates the key
        run.investor_key.chmod(0o644)
        n = len(run.ledger.read_bytes().splitlines())
        with pytest.raises(
            SigningError, match="chmod 600"
        ):  # an unsignable decision is not written
            ledger.append(investor("topped_up"))
        assert len(run.ledger.read_bytes().splitlines()) == n
        with pytest.raises(SigningError):  # money records are durable before the anchor is tried
            ledger.append(boss_call(5_000))
        assert len(run.ledger.read_bytes().splitlines()) == n + 1


# --- a forgery is refused at the one place every reader gets its events from ------------------


@pytest.mark.parametrize("how", ["none", "made-up", "first-form", "copied"])
@pytest.mark.parametrize("name", INVESTOR)
def test_an_investor_event_forged_with_the_chain_recomputed_is_refused(run, name, how):
    genuine = honest(run, boss_call(), investor("topped_up"))[-1]
    forged = forgery_of(name, how, genuine)
    attacker(run, boss_call(), forged)
    with pytest.raises(
        LedgerUnverifiedError, match=r"ledger\.jsonl:2: investor .* does not verify"
    ):
        run.events()
    with pytest.raises(LedgerUnverifiedError):
        read_events(run.ledger, run.investor_key)
    assert read_events(run.ledger)[1].data.get("ruling") == forged.data.get("ruling")  # chain only


def test_a_forgery_anywhere_in_a_long_ledger_names_its_line(run):
    honest(run, boss_call(), investor("resumed"))
    attacker(run, *([boss_call()] * 5), investor("topped_up"), *([boss_call()] * 3))
    with pytest.raises(LedgerUnverifiedError, match=r"ledger\.jsonl:6:"):
        run.events()


def test_the_message_names_the_line_and_never_the_key(run):
    honest(run, boss_call(), investor("resumed"))
    secret = run.investor_key.read_text().strip()
    attacker(run, investor("resumed"))
    with pytest.raises(LedgerUnverifiedError) as raised:
        run.events()
    assert secret not in str(raised.value) and "ledger.jsonl:1" in str(raised.value)


@pytest.mark.parametrize("name", ["topped_up", "resumed", "ruled-dropped", "stopped"])
def test_a_genuine_signed_event_replayed_or_moved_is_refused(run, name):
    genuine = honest(run, boss_call(), investor(name), boss_call(5_000))[1]
    for replay in (
        [boss_call(), genuine, genuine],  # twice: the budget would double
        [boss_call(), boss_call(5_000), genuine],  # moved after a later line
        [genuine, boss_call()],  # moved to the front
        [boss_call(), genuine, boss_call(5_000), genuine],  # again, later
    ):
        attacker(run, *replay)
        with pytest.raises(LedgerUnverifiedError, match="does not verify"):
            run.events()


def test_a_signed_event_authenticates_every_line_before_it(run):
    """An edit before a signed event, even with the chain recomputed, voids the event: its
    signature covers the hash of the line before it."""
    events = honest(run, boss_call(), boss_call(5_000), investor("topped_up"))
    attacker(run, dataclasses.replace(events[0], cost_micros=0), *events[1:])
    with pytest.raises(LedgerUnverifiedError, match=r"ledger\.jsonl:3:"):
        run.events()


def test_a_signed_event_from_another_run_or_round_or_actor_is_refused(run):
    genuine = honest(run, boss_call(), investor("topped_up"))[1]
    for moved in (
        dataclasses.replace(genuine, run="r2"),
        dataclasses.replace(genuine, round=2),
        dataclasses.replace(genuine, event=EventType.RESUMED),
        dataclasses.replace(genuine, data={"micros": 2_000_000, "sig": genuine.data["sig"]}),
    ):
        attacker(run, boss_call(), moved)
        with pytest.raises(LedgerUnverifiedError):
            run.events()


def test_an_attacker_with_a_key_of_their_own_is_refused(run, tmp_path):
    honest(run, boss_call(), investor("resumed"))
    run.ledger.unlink()
    other = tmp_path / "elsewhere" / ".boss" / "investor.key"
    with LedgerWriter(run.ledger, other) as ledger:
        ledger.append(boss_call())
        ledger.append(investor("topped_up"))
    with pytest.raises(LedgerUnverifiedError, match="does not verify"):
        run.events()


def test_a_signed_event_is_refused_when_the_key_is_gone_or_replaced(run):
    honest(run, boss_call(), investor("topped_up"))
    run.investor_key.unlink()
    with pytest.raises(LedgerUnverifiedError, match="does not verify"):
        run.events()
    signing.load_or_create_key(run.investor_key)  # a fresh key cannot vouch for the old events
    with pytest.raises(LedgerUnverifiedError, match="does not verify"):
        run.events()


def test_a_damaged_key_stops_the_read_instead_of_skipping_it(run):
    honest(run, boss_call(), investor("topped_up"))
    run.investor_key.chmod(0o644)
    with pytest.raises(LedgerUnverifiedError, match="chmod 600"):
        run.events()


# --- the readers: a forgery would change their answer, and never reaches them ------------------

READERS = {
    "rulings.ruled": (
        "ruled-dropped",
        lambda ev: rulings.ruled(ev, rulings.DROPPED),
        frozenset(),
    ),
    "budget.round_budget": ("topped_up", lambda ev: budget.round_budget(SHEET, ev, 1), 300_000),
    "state._stopped (a resume lifts a stop)": (
        "resumed",
        lambda ev: run_state(ev, ["t1"]).stopped,
        True,
    ),
    "state.approved_rounds (a round's funding)": (
        "round-approved",
        lambda ev: run_state(ev, ["t1"]).approved_rounds,
        frozenset(),
    ),
    "state._closed_rounds (a top-up reopens a lock)": (
        "topped_up",
        lambda ev: run_state(ev, ["t1"]).locked_rounds,
        frozenset({1}),
    ),
    "pipeline._settled (a declined fix round)": ("ruled-declined", pipeline._settled, 0),
    "pipeline._settled (an approved amendment)": ("amendment-approved", pipeline._settled, 0),
}


def critic_call() -> Event:
    data = {"role": "critic", "verified": 1}
    return Event(run="r1", round=0, actor="role:critic", event=EventType.ROLE_CALL, data=data)


def prefix(name: str) -> list[Event]:
    """Events that put each reader in the state where the investor's event matters."""
    closed = Event(
        run="r1", round=1, actor="rule", event=EventType.ROUND_CLOSED, data={"unlocked": False}
    )
    stop = Event(run="r1", round=1, actor="rule", event=EventType.STOPPED, data={"reason": "x"})
    return {
        "resumed": [stop],
        "topped_up": [closed],
        "ruled-declined": [critic_call()],
        "amendment-approved": [critic_call()],
    }.get(name, [])


@pytest.mark.parametrize("reader", READERS)
def test_each_reader_acts_on_the_genuine_event_and_never_sees_a_forged_one(run, reader):
    name, read, without = READERS[reader]
    forged = forgery_of(name, "none")
    # the control: without the investor's event the reader says one thing ...
    assert read(prefix(name)) == without
    # ... with the genuine, signed event it acts on it ...
    genuine = honest(run, *prefix(name), investor(name))
    assert read(genuine) != without, "the reader must care about this event, or the test is vacuous"
    # ... and a forged one never reaches it: the boundary refuses the whole ledger.
    attacker(run, *prefix(name), forged)
    with pytest.raises(LedgerUnverifiedError):
        read(run.events())


# --- older ledgers keep loading ---------------------------------------------------------------


def legacy_line(run: RunPaths, name: str, signed: bool) -> bytes:
    """A line written before the chain existed (no `prev`), the way the old code wrote it."""
    event = investor(name)
    if signed:
        key = signing.load_or_create_key(run.investor_key)
        event = dataclasses.replace(
            event, data={**event.data, "sig": signing._digest_v1(key, event)}
        )
    return (event.to_json() + "\n").encode()


@pytest.mark.parametrize("name", INVESTOR)
def test_unsigned_investor_events_older_than_the_chain_still_load_with_a_key_present(run, name):
    signing.load_or_create_key(run.investor_key)
    run.ledger.parent.mkdir(parents=True, exist_ok=True)
    run.ledger.write_bytes(legacy_line(run, name, signed=False))
    [event] = run.events()
    assert event.prev is None and "sig" not in event.data


def test_a_chained_unsigned_investor_event_is_refused_once_a_key_exists(run):
    signing.load_or_create_key(run.investor_key)
    attacker(run, boss_call(), investor("resumed"))  # `prev` set, no signature
    with pytest.raises(LedgerUnverifiedError, match=r"ledger\.jsonl:2:"):
        run.events()


def test_an_approval_signed_in_the_first_form_still_loads_and_nothing_else_does(run):
    key = signing.load_or_create_key(run.investor_key)
    approval = investor("round-approved")
    sig = signing._digest_v1(key, approval)
    chained = dataclasses.replace(approval, data={**approval.data, "sig": sig})
    attacker(run, boss_call(), chained)
    assert run.events()[1].data["sig"] == sig
    # the same first-form signature on another kind of event is refused, in the chain or out of it
    for kind in (EventType.RESUMED, EventType.TOPPED_UP, EventType.RULED, EventType.STOPPED):
        attacker(run, boss_call(), dataclasses.replace(chained, event=kind))
        with pytest.raises(LedgerUnverifiedError):
            run.events()


def test_a_ledger_with_no_key_and_no_signature_loads_as_it_always_did(run):
    attacker(run, boss_call(), investor("topped_up"))
    assert not run.investor_key.exists()
    assert len(run.events()) == 2


def test_a_folder_that_is_not_in_a_project_has_no_key_to_check(tmp_path):
    folder = RunPaths(tmp_path / "run")
    assert folder.investor_key is None
    with folder.writer() as ledger:
        ledger.append(investor("topped_up"))
    assert len(folder.events()) == 1 and "sig" not in folder.events()[0].data


# --- seeded fuzz: any tampering with a ledger that has signed events is refused or harmless ----


def lines_of(run: RunPaths) -> list[bytes]:
    return run.ledger.read_bytes().split(b"\n")[:-1]


@pytest.mark.parametrize("seed", range(25))
def test_fuzz_no_edit_of_a_signed_ledger_changes_what_a_reader_gets_without_being_refused(
    run, seed
):
    rng = random.Random(seed)
    names = rng.sample(sorted(INVESTOR), 4)
    events = honest(
        run, boss_call(), investor(names[0]), boss_call(5_000), investor(names[1]),
        boss_call(6_000), investor(names[2]), investor(names[3]),
    )  # fmt: skip
    original = events  # the edits below keep the last line: dropping it is the anchor's job
    # the attacker rewrites with a valid chain: delete, duplicate or swap lines, edit a boss cost
    edited = list(original)
    op = rng.choice(["delete", "duplicate", "swap", "cost", "data"])
    i = rng.randrange(len(edited) - 1)
    if op == "delete":
        del edited[i]
    elif op == "duplicate":
        edited.insert(i, edited[i])
    elif op == "swap":
        edited[i], edited[i + 1] = edited[i + 1], edited[i]
    elif op == "cost":
        j = rng.choice([0, 2, 4])
        edited[j] = dataclasses.replace(edited[j], cost_micros=rng.randrange(1, 9) * 1_000)
    else:
        j = rng.choice([1, 3, 5, 6])
        edited[j] = dataclasses.replace(edited[j], data={**edited[j].data, "extra": rng.random()})
    attacker(run, *edited)
    try:
        got = run.events()
    except LedgerUnverifiedError:
        return
    assert got == original  # not refused only when the edit changed nothing


# --- through the real CLI ----------------------------------------------------------------------


def forge_topup(boss, micros=900_000):
    """Append, with a valid chain and no key, the top-up a worker would write."""
    [run_dir] = boss.runs()
    with LedgerWriter(run_dir / "ledger.jsonl") as ledger:
        ledger.append(
            Event(run=run_dir.name, round=1, actor="investor", event=EventType.TOPPED_UP,
                  data={"micros": micros})
        )  # fmt: skip
    return run_dir


def test_a_real_run_topped_up_and_resumed_verifies_throughout(boss):
    locked_run(boss)
    code, output = boss("topup", "--round", "1", "--amount", "0.20")
    assert code == EXIT_OK, output
    code, output = boss("resume")
    assert code in (EXIT_OK, EXIT_INCOMPLETE), output
    [run_dir] = boss.runs()
    key = load_key(RunPaths(run_dir).investor_key)
    signed_events = [e for e in events_of_run(boss) if e.actor == "investor"]
    assert [e.event for e in signed_events] == [EventType.APPROVED, EventType.TOPPED_UP]
    assert all(signing.verify(key, e) for e in signed_events)
    code, output = boss("report")
    assert code == EXIT_OK, output


@pytest.mark.parametrize(
    "command",
    [("resume",), ("report",), ("status",), ("topup", "--round", "1", "--amount", "0.01")],
)
def test_a_forged_top_up_stops_every_command_that_reads_the_ledger_and_spends_nothing(
    boss, command
):
    locked_run(boss)
    started = slices_started(boss)
    forge_topup(boss)
    before = (boss.runs()[0] / "ledger.jsonl").read_bytes()
    code, output = boss(*command)
    assert code == EXIT_FAILED and "does not verify" in output, output
    assert (boss.runs()[0] / "ledger.jsonl").read_bytes() == before  # nothing was appended
    assert (
        sum(e.event is EventType.SLICE_START for e in read_events(boss.runs()[0] / "ledger.jsonl"))
        == started
    )


def test_a_forged_resume_cannot_lift_a_stop(boss):
    boss("fund", "Reverse a string.", "--budget", "0.50", "--max-minutes", "1e-9")
    [run_dir] = boss.runs()
    with LedgerWriter(run_dir / "ledger.jsonl") as ledger:
        ledger.append(Event(run=run_dir.name, round=0, actor="investor", event=EventType.RESUMED))
    code, output = boss("resume")
    assert code == EXIT_FAILED and "does not verify" in output, output
    assert slices_started(boss) == 0


def test_fuzz_values_that_are_not_ints_in_a_signed_top_up_never_raise_anything_but_the_refusal(run):
    signing.load_or_create_key(run.investor_key)
    for micros in (True, 1.5, "200000", None, -5, [1], {"a": 1}, 10**40):
        attacker(
            run, boss_call(), dataclasses.replace(investor("topped_up"), data={"micros": micros})
        )
        with pytest.raises(LedgerUnverifiedError):
            run.events()


def test_the_genesis_value_is_what_a_signature_of_the_first_line_covers(run):
    [first] = honest(run, investor("resumed"))
    assert first.prev == GENESIS and signing.verify(load_key(run.investor_key), first)
