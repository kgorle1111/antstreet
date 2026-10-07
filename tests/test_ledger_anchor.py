"""The ledger's anchor: an HMAC of its line count and last line hash (T46).

The hash chain cannot see the end of the file: nothing follows the last line, so an edit to it or
a cut that drops trailing lines leaves a valid chain. The writer therefore records, after every
append, `<project>/.boss/anchors/<run>`: the line count and the last line's hash, keyed by the
investor key. A reader that passes the key path refuses a ledger whose first `lines` lines are not
the ones recorded. The limits that remain are pinned as `test_accepted_risk_*`.
"""

import dataclasses
import hashlib
import json
import os
import random
import re
import stat
import threading

import pytest

from boss import signing
from boss.ledger import (
    Event,
    EventType,
    LedgerCorruptError,
    LedgerUnverifiedError,
    LedgerWriter,
    adopt_unsigned,
    read_events,
    repair_torn_tail,
    unsigned_lines,
)
from boss.rundir import RunPaths
from boss.signing import anchor_path, load_key, load_or_create_key, read_anchor, write_anchor

TS = "2026-10-02T11:00:00+00:00"  # fixed: an edit must not hide behind a clock tick


@pytest.fixture
def run(tmp_path):
    return RunPaths(tmp_path / "project" / ".boss" / "runs" / "r1")


def boss_call(n: int = 1) -> Event:
    return Event(
        run="r1", round=0, actor="boss", event=EventType.BOSS_CALL, cost_micros=n * 1_000, ts=TS
    )


def resumed() -> Event:
    return Event(run="r1", round=1, actor="investor", event=EventType.RESUMED, ts=TS)


def honest(run: RunPaths, *events: Event) -> list[Event]:
    with run.writer() as ledger:
        for event in events:
            ledger.append(event)
    return run.events()


def ledger_of(run: RunPaths, n: int = 6) -> list[bytes]:
    """n lines through the real writer, an investor event first so the key and the anchor exist."""
    honest(run, resumed(), *[boss_call(i) for i in range(1, n)])
    return lines_of(run)


def lines_of(run: RunPaths) -> list[bytes]:
    return run.ledger.read_bytes().split(b"\n")[:-1]


def put(run: RunPaths, lines: list[bytes]) -> None:
    run.ledger.write_bytes(b"".join(line + b"\n" for line in lines))


def sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def anchor_file(run: RunPaths):
    return anchor_path(run.investor_key, run.root.name)


def refused(run: RunPaths, match: str):
    with pytest.raises(LedgerUnverifiedError, match=match) as raised:
        run.events()
    return raised


# --- what is written ---------------------------------------------------------------------------


def test_the_anchor_follows_every_append_from_the_first_line(run):
    with run.writer() as ledger:  # the writer creates the key when it opens
        for n in range(1, 6):
            ledger.append(resumed() if n == 2 else boss_call(n))
            lines = lines_of(run)
            found = read_anchor(run.investor_key, load_key(run.investor_key), "r1")
            assert (found.lines, found.last) == (len(lines), sha(lines[-1]))  # type: ignore[union-attr]


def test_the_anchor_is_a_private_file_holding_no_secret_and_no_temporary_is_left(run):
    ledger_of(run)
    secret = run.investor_key.read_text().strip()
    body = anchor_file(run).read_text()
    assert set(json.loads(body)) == {"lines", "last", "mac"} and secret not in body
    assert stat.S_IMODE(anchor_file(run).stat().st_mode) == 0o600
    assert [p.name for p in anchor_file(run).parent.iterdir()] == ["r1"]


def test_each_run_has_its_own_anchor_under_the_one_project_key(run):
    other = RunPaths(run.root.parent / "r2")
    ledger_of(run)
    honest(other, dataclasses.replace(resumed(), run="r2"))
    assert sorted(p.name for p in anchor_file(run).parent.iterdir()) == ["r1", "r2"]
    assert len(other.events()) == 1 and len(run.events()) == 6


def test_a_writer_without_a_key_path_writes_no_anchor(tmp_path):
    path = tmp_path / ".boss" / "runs" / "r1" / "ledger.jsonl"
    with LedgerWriter(path) as ledger:
        ledger.append(boss_call())
    assert not (tmp_path / ".boss" / "anchors").exists()


def test_the_anchor_survives_threads_appending_and_a_reader_racing_them(run):
    """The writer appends and then re-anchors; the reader reads the anchor and then the ledger.
    Whatever the interleaving, the ledger is never behind the anchor the reader holds."""
    honest(run, resumed())
    failures, stop = [], threading.Event()

    def read_forever():
        while not stop.is_set():
            try:
                run.events()
            except Exception as exc:
                failures.append(exc)
                return

    reader = threading.Thread(target=read_forever)
    reader.start()
    with run.writer() as ledger:
        workers = [
            threading.Thread(target=lambda: [ledger.append(boss_call()) for _ in range(15)])
            for _ in range(3)
        ]
        for t in workers:
            t.start()
        for t in workers:
            t.join()
    stop.set()
    reader.join()
    assert failures == []
    lines = lines_of(run)
    found = read_anchor(run.investor_key, load_key(run.investor_key), "r1")
    assert len(lines) == 46 and (found.lines, found.last) == (46, sha(lines[-1]))  # type: ignore[union-attr]


# --- a dropped tail and an edited last line are refused ----------------------------------------


@pytest.mark.parametrize("dropped", range(1, 7))
def test_dropped_trailing_lines_are_refused_with_the_line_count(run, dropped):
    lines = ledger_of(run, 6)
    put(run, lines[: 6 - dropped])  # every remaining line still chains: the chain alone passes
    assert len(read_events(run.ledger)) == 6 - dropped
    refused(
        run, rf"has {6 - dropped} lines but its anchor records 6: {dropped} line\(s\) were dropped"
    )


def test_an_edited_last_line_is_refused_though_nothing_follows_it(run):
    lines = ledger_of(run, 4)
    edited = Event.from_json(lines[-1].decode())
    put(run, [*lines[:-1], dataclasses.replace(edited, cost_micros=0).to_json().encode()])
    assert len(read_events(run.ledger)) == 4  # a valid chain
    refused(run, r"line 4 is not the line its anchor records \(it was edited\)")


def test_a_last_line_replaced_by_another_is_refused(run):
    lines = ledger_of(run, 4)
    forged = dataclasses.replace(boss_call(9), prev=sha(lines[-2]))
    put(run, [*lines[:-1], forged.to_json().encode()])
    refused(run, "line 4 is not the line its anchor records")


def test_dropping_the_tail_and_appending_forged_lines_to_make_up_the_count_is_refused(run):
    lines = ledger_of(run, 6)
    put(run, lines[:3])
    with LedgerWriter(run.ledger) as ledger:  # a keyless writer: the chain is valid, the count is 6
        for n in range(3):
            ledger.append(boss_call(50 + n))
    assert len(read_events(run.ledger)) == 6
    refused(run, "line 6 is not the line its anchor records")


def test_any_line_changed_up_to_the_anchor_is_refused_even_with_the_chain_recomputed(run):
    lines = ledger_of(run, 6)
    events = [Event.from_json(line.decode()) for line in lines]
    for i in range(5):  # the investor event's own signature already refuses i == 0
        run.ledger.unlink()
        edited = [
            dataclasses.replace(e, cost_micros=7_000) if j == i else e for j, e in enumerate(events)
        ]
        with LedgerWriter(run.ledger) as ledger:
            for e in edited:
                ledger.append(e)
        with pytest.raises(LedgerUnverifiedError):
            run.events()


@pytest.mark.parametrize("seed", range(30))
def test_fuzz_no_cut_of_a_ledger_that_chains_is_accepted(run, seed):
    rng = random.Random(seed)
    n = rng.randrange(2, 30)
    signed_at = rng.randrange(n)  # an investor event somewhere: it creates the key
    events = [resumed() if i == signed_at else boss_call(i + 1) for i in range(n)]
    honest(run, *events)
    lines = lines_of(run)
    keep = rng.randrange(0, n)  # always fewer than all of them
    put(run, lines[:keep])
    assert len(read_events(run.ledger)) == keep  # the chain alone accepts every cut
    with pytest.raises(
        LedgerUnverifiedError, match=rf"has {keep} lines but its anchor records {n}"
    ):
        run.events()


# --- the anchor itself ------------------------------------------------------------------------


def test_an_edited_anchor_is_refused(run):
    ledger_of(run, 4)
    body = json.loads(anchor_file(run).read_text())
    for change in ({"lines": 3}, {"lines": 5}, {"last": "0" * 64}, {"mac": "0" * 64}):
        anchor_file(run).write_text(json.dumps(body | change))
        refused(run, "does not verify against the investor key")


def test_an_anchor_made_with_another_key_or_for_another_run_is_refused(run, tmp_path):
    lines = ledger_of(run, 4)
    forged = tmp_path / "forged" / ".boss" / "investor.key"
    load_or_create_key(forged)
    write_anchor(forged, "r1", 2, sha(lines[1]))  # a keyless attacker's own key: lines 2, valid
    anchor_file(run).write_bytes(anchor_path(forged, "r1").read_bytes())
    refused(run, "does not verify")
    other = RunPaths(run.root.parent / "r2")
    honest(other, dataclasses.replace(resumed(), run="r2"))
    anchor_file(run).write_bytes(anchor_path(run.investor_key, "r2").read_bytes())
    refused(run, "does not verify")  # moved from the run it was written for


@pytest.mark.parametrize(
    "garbage",
    [b"", b"{", b"null", b"[]", b'{"lines": 1}', b'{"lines": true, "last": "a", "mac": "b"}',
     b'{"lines": "4", "last": "a", "mac": "b"}', b'{"lines": 4, "last": 5, "mac": "b"}',
     b'{"lines": 4, "last": "a", "mac": 7}', b'{"lines": 4, "last": "a", "mac": "\xc3\xa9"}',
     b"\xff\xfe", b"x" * 100_000],
)  # fmt: skip
def test_a_garbage_anchor_is_a_refusal_and_never_a_crash(run, garbage):
    ledger_of(run, 3)
    anchor_file(run).write_bytes(garbage)
    refused(run, "does not verify|cannot read")


def test_a_missing_anchor_is_refused_for_a_ledger_that_was_written_with_anchors(run):
    ledger_of(run, 3)
    anchor_file(run).unlink()
    error = refused(run, "is missing, so dropped lines could not be seen")
    assert str(anchor_file(run)) in str(error.value)


def test_an_older_run_with_no_anchor_is_refused_until_the_investor_adopts_it(run, tmp_path):
    # an older run: chained, an approval signed in the first form, no anchor
    key = load_or_create_key(run.investor_key)
    approval = Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data={"x": 1})
    old = dataclasses.replace(approval, data={"x": 1, "sig": signing._digest_v1(key, approval)})
    with LedgerWriter(run.ledger) as ledger:
        ledger.append(boss_call())
        ledger.append(old)
        ledger.append(boss_call(2))
    refused(run, r"3 of 3 lines are unsigned .* `boss verify r1 --adopt-unsigned`")
    assert adopt_unsigned(run.ledger, run.investor_key) == 3
    assert len(run.events()) == 3 and adopt_unsigned(run.ledger, run.investor_key) == 0
    # a run that has not been approved yet: boss calls only, and no key at all
    fresh = RunPaths(tmp_path / "other" / ".boss" / "runs" / "r9")
    with fresh.writer() as ledger:
        ledger.append(boss_call())
    assert len(fresh.events()) == 1


def test_resuming_an_older_run_starts_anchoring_it_from_the_first_new_line(run):
    key = load_or_create_key(run.investor_key)
    approval = Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data={"x": 1})
    old = dataclasses.replace(approval, data={"x": 1, "sig": signing._digest_v1(key, approval)})
    with LedgerWriter(run.ledger) as ledger:
        ledger.append(old)
    adopt_unsigned(run.ledger, run.investor_key)
    honest(run, resumed())  # the first line the new code writes
    assert read_anchor(run.investor_key, key, "r1").lines == 2  # type: ignore[union-attr]
    put(run, lines_of(run)[:1])
    refused(run, "has 1 lines but its anchor records 2")


def test_the_stamped_rule_alone_refuses_a_signed_run_whose_anchor_and_last_line_are_gone(run):
    honest(run, boss_call(), boss_call(2), boss_call(3))  # signed lines, no investor event
    anchor_file(run).unlink()
    put(run, lines_of(run)[:2])
    refused(run, r"its anchor .* is missing")


def test_a_writer_refuses_an_unanchored_unsigned_ledger_even_with_the_key_gone(run):
    honest(run, boss_call(), boss_call(2), boss_call(3))
    stripped = [unsigned(line) for line in lines_of(run)]
    put(run, rechain(stripped, 0, keep_macs=False))
    anchor_file(run).unlink()
    run.investor_key.unlink()  # nothing left to check against: the read accepts it ...
    assert len(run.events()) == 3
    with pytest.raises(LedgerUnverifiedError, match="--adopt-unsigned"), run.writer():
        pytest.fail("a new key would sign on top of a ledger nobody vouched for")
    assert not run.investor_key.exists()


def test_adopting_never_accepts_a_forged_signed_line_or_creates_a_key_over_lost_signatures(run):
    ledger_of(run, 3)
    anchor_file(run).unlink()
    run.investor_key.unlink()
    with pytest.raises(LedgerUnverifiedError, match="key is missing; restore"):
        adopt_unsigned(run.ledger, run.investor_key)
    assert not run.investor_key.exists()


def test_an_anchor_with_the_key_deleted_is_refused(run):
    honest(run, boss_call(), boss_call(2))  # no investor event: nothing is signed
    load_or_create_key(run.investor_key)
    honest(run, boss_call(3))  # the first anchor
    run.investor_key.unlink()
    refused(run, "has an anchor but the investor key is missing|key is missing; restore")


# --- the writer never appends to a ledger the key does not vouch for ---------------------------


def test_a_writer_refuses_a_ledger_with_a_dropped_tail_so_nothing_is_laundered(run):
    lines = ledger_of(run, 6)
    put(run, lines[:3])
    before = run.ledger.read_bytes()
    with (
        pytest.raises(LedgerUnverifiedError, match="3 lines but its anchor records 6"),
        run.writer(),
    ):
        pytest.fail("opened")
    assert run.ledger.read_bytes() == before
    assert read_anchor(run.investor_key, load_key(run.investor_key), "r1").lines == 6  # type: ignore[union-attr]
    with LedgerWriter(run.ledger):  # and the lock was released: a plain writer still opens
        pass


def test_a_crash_between_the_line_and_its_anchor_is_not_a_tamper_and_the_next_append_heals_it(run):
    lines = ledger_of(run, 4)
    older = anchor_file(run).read_bytes()
    honest(run, boss_call(9))  # 5 lines, anchor says 5 ...
    anchor_file(run).write_bytes(
        older
    )  # ... as if the anchor write of the last append never landed
    assert len(run.events()) == 5 and len(lines) == 4
    honest(run, boss_call(10))
    found = read_anchor(run.investor_key, load_key(run.investor_key), "r1")
    assert found.lines == 6  # type: ignore[union-attr]
    run.events()


def test_a_cut_off_last_line_is_repaired_without_disturbing_the_anchor(run):
    ledger_of(run, 4)
    with run.ledger.open("ab") as fh:
        fh.write(b'{"v": 1, "run": "r1", "rou')  # a hard kill in the middle of an append
    assert repair_torn_tail(run.ledger) is not None
    assert len(run.events()) == 4


def test_a_failing_anchor_write_loses_no_line(run, tmp_path):
    ledger_of(run, 2)
    anchor_file(run).parent.chmod(0o500)  # the anchor cannot be replaced
    try:
        with run.writer() as ledger, pytest.raises(OSError):
            ledger.append(boss_call(5))
    finally:
        anchor_file(run).parent.chmod(0o700)
    assert len(lines_of(run)) == 3  # the money record is durable; the next read says why it is odd
    assert len(run.events()) == 3  # one line past the anchor is not vouched for, and not refused


# --- every line is signed ------------------------------------------------------------------------

MAC_TAIL = re.compile(rb', "mac": "[0-9a-f]{64}"\}\Z')


def unsigned(line: bytes) -> bytes:
    return MAC_TAIL.sub(b"}", line)


def rechain(lines: list[bytes], start: int = 0, *, keep_macs: bool) -> list[bytes]:
    """What a forger without the key can do: recompute every `prev` from `start` on, keeping each
    line's old `mac` or dropping it."""
    out = lines[:start]
    for line in lines[start:]:
        raw = json.loads(unsigned(line))
        raw["prev"] = sha(out[-1]) if out else "0" * 64
        body = json.dumps(raw, sort_keys=True).encode()
        mac = MAC_TAIL.search(line)
        out.append(body[:-1] + mac.group(0) if keep_macs and mac else body)
    return out


def test_every_line_a_project_writer_appends_carries_a_mac_that_verifies(run):
    lines = ledger_of(run, 5)
    key = load_key(run.investor_key)
    assert key is not None
    for line in lines:
        mac = MAC_TAIL.search(line)
        assert mac, line
        assert signing.verify_line(key, "r1", sha(unsigned(line)), mac.group(0)[10:74].decode())
        assert not signing.verify_line(key, "r2", sha(unsigned(line)), mac.group(0)[10:74].decode())
    assert unsigned_lines(run.ledger) == 0 and len(run.events()) == 5


def test_the_line_mac_is_a_fixed_function_of_the_key_the_run_and_the_line_hash():
    assert signing.line_mac(b"k" * 32, "r1", "a" * 64) == (
        "ad063cac72245602c330bb60df102acf476eabe921091dbd9c54d334eb76fa78"
    )


@pytest.mark.parametrize("target", range(5))
def test_a_line_edited_with_the_chain_recomputed_and_the_macs_kept_is_refused(run, target):
    lines = ledger_of(run, 5)
    raw = json.loads(unsigned(lines[target]))
    raw["cost_micros"] = (raw["cost_micros"] or 0) + 1
    lines[target] = json.dumps(raw, sort_keys=True).encode()[:-1] + MAC_TAIL.search(
        lines[target]
    ).group(0)
    put(run, rechain(lines, target + 1, keep_macs=True))
    refused(run, "does not verify|is not the line its anchor records")


def test_a_whole_ledger_rewritten_consistently_without_the_key_is_refused(run):
    lines = ledger_of(run, 5)
    raw = json.loads(unsigned(lines[2]))
    raw["cost_micros"] = 1
    lines[2] = json.dumps(raw, sort_keys=True).encode()
    for keep in (True, False):
        put(run, rechain(lines, 0, keep_macs=keep))
        refused(run, "does not verify|unsigned line|is not the line its anchor records")


def test_a_signed_line_from_another_run_of_the_same_project_is_refused(run, tmp_path):
    ledger_of(run, 3)
    other = RunPaths(run.root.parent / "r2")
    honest(other, Event(run="r1", round=0, actor="boss", event=EventType.BOSS_CALL, ts=TS))
    put(run, [*lines_of(run), *lines_of(other)])  # the chain breaks too; rechain to isolate the mac
    put(run, rechain(lines_of(run), 3, keep_macs=True))
    refused(run, r"ledger\.jsonl:4: a line whose signature does not verify")


def test_a_mac_anywhere_but_the_end_of_the_line_makes_the_line_corrupt(run):
    lines = ledger_of(run, 2)
    raw = json.loads(lines[1])
    put(run, [lines[0], json.dumps(raw, sort_keys=True).encode()])  # `mac` moved among the keys
    with pytest.raises(LedgerCorruptError, match=r"ledger\.jsonl:2: fields differ .*\['mac'\]"):
        run.events()


def test_signed_lines_with_the_key_gone_say_to_restore_it(run):
    ledger_of(run, 3)
    run.investor_key.unlink()
    anchor_file(run).unlink()
    refused(run, r"lines are signed but the investor key is missing; restore .*investor\.key")


def test_signed_lines_with_the_key_replaced_are_refused(run):
    ledger_of(run, 3)
    run.investor_key.unlink()
    anchor_file(run).unlink()
    load_or_create_key(run.investor_key)
    refused(run, r"ledger\.jsonl:1: .*does not verify .*or the key was replaced")


def test_an_older_unsigned_ledger_still_loads_says_so_and_is_signed_from_its_next_line(run):
    with LedgerWriter(run.ledger) as ledger:  # written before every line was signed
        ledger.append(boss_call())
        ledger.append(boss_call(2))
    assert unsigned_lines(run.ledger) == 2 and len(run.events()) == 2  # no key yet: nothing checks
    load_or_create_key(run.investor_key)
    refused(run, "--adopt-unsigned")
    assert adopt_unsigned(run.ledger, run.investor_key) == 2  # the investor vouches for it
    honest(run, boss_call(3))  # resumed by this code: the new line covers the two before it
    assert MAC_TAIL.search(lines_of(run)[-1]) and unsigned_lines(run.ledger) == 2
    put(run, [*lines_of(run)[:2], unsigned(lines_of(run)[2])])  # and its mac cannot be stripped
    refused(run, "is not the line its anchor records")


def test_the_report_names_a_ledger_no_line_signature_covers(run):
    from boss.cli import _report_text

    with LedgerWriter(run.ledger) as ledger:
        ledger.append(boss_call())
    text, _ = _report_text(run, run.events())
    assert "Ledger: 1 of 1 lines are unsigned: either older than line signing or rewritten" in text
    adopt_unsigned(run.ledger, run.investor_key)
    honest(run, boss_call(2))
    text, _ = _report_text(run, run.events())
    assert "Ledger: 1 of 2 lines are unsigned" in text
    fresh = RunPaths(run.root.parent / "r2")
    honest(fresh, boss_call())
    assert "Ledger:" not in _report_text(fresh, fresh.events())[0]


# --- what the anchor does not protect ---------------------------------------------------------


def test_lines_appended_after_the_last_anchor_without_the_key_are_refused(run):
    ledger_of(run, 3)
    with LedgerWriter(run.ledger) as ledger:  # a keyless writer appends a forged check result
        ledger.append(Event(run="r1", round=1, actor="gate", event=EventType.CHECK_RESULT,
                            data={"check": "c01", "status": "passed"}))  # fmt: skip
    refused(run, r"ledger\.jsonl:4: an unsigned line after signed ones")
    with pytest.raises(LedgerUnverifiedError), run.writer():  # and the writer never re-anchors it
        pytest.fail("opened")


def test_accepted_risk_an_older_genuine_anchor_with_its_ledger_prefix_is_a_valid_rollback(run):
    lines = ledger_of(run, 4)
    anchor, old_lines = anchor_file(run).read_bytes(), lines[:]
    honest(run, boss_call(8), boss_call(9))
    put(run, old_lines)  # the ledger and its anchor, both put back as they were
    anchor_file(run).write_bytes(anchor)
    assert len(run.events()) == 4  # a rollback to a state that was once genuine is not seen


def test_accepted_risk_whoever_holds_the_key_can_write_signed_events_and_a_matching_anchor(run):
    ledger_of(run, 4)
    run.ledger.unlink()
    anchor_file(run).unlink()  # the writer would refuse a ledger that no longer matches its anchor
    honest(run, boss_call(), Event(run="r1", round=1, actor="investor", event=EventType.TOPPED_UP,
                                   data={"micros": 10**9}))  # fmt: skip
    assert run.events()[-1].data["micros"] == 10**9  # T29 and T46: the key is the whole defence


def test_accepted_risk_a_rewritten_ledger_with_its_anchor_gone_loads_once_the_investor_adopts_it(
    run,
):
    ledger_of(run, 4)
    forged = Event(
        run="r1", round=1, actor="investor", event=EventType.TOPPED_UP, data={"micros": 5}
    )
    run.ledger.write_bytes((forged.to_json() + "\n").encode())  # no `prev`, no signature
    for path in anchor_file(run).parent.iterdir():
        path.unlink()
    refused(run, "--adopt-unsigned")  # the downgrade needs a human decision ...
    adopt_unsigned(run.ledger, run.investor_key)
    assert run.events()[0].data == {"micros": 5}  # ... and the human cannot tell it from old
    assert os.path.exists(run.investor_key)


def test_boss_verify_refuses_an_unanchored_old_run_until_adopt_unsigned_is_given(run):
    from boss import cli

    with LedgerWriter(run.ledger) as ledger:  # an old run: unsigned, no anchor
        ledger.append(boss_call())
    load_or_create_key(run.investor_key)
    project = run.root.parent.parent.parent
    said: list[str] = []
    assert cli.main(["verify", "r1", "--dir", str(project)], say=said.append) == 1
    assert "--adopt-unsigned" in said[-1]
    said.clear()
    assert cli.main(["verify", "r1", "--adopt-unsigned", "--dir", str(project)],
                    say=said.append) == 0  # fmt: skip
    assert said[0].startswith("Run r1: adopted 1 unsigned lines") and "verifies" in said[-1]
