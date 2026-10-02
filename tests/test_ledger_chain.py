"""The ledger's hash chain: each line carries the SHA-256 of the line before it.

The chain is unkeyed, so it detects an edit that does not recompute it (a byte flip, a deleted,
inserted or reordered line) and does not stop one that does (T29). It also cannot see the end of
the file: nothing follows the last line, and dropping trailing lines leaves a valid chain; those
two limits are pinned by `test_accepted_risk_*` below.
"""

import hashlib
import json
import random
import threading

import pytest

from boss.ledger import (
    GENESIS,
    Event,
    EventType,
    LedgerCorruptError,
    LedgerWriter,
    read_events,
    repair_torn_tail,
)


def ev(**overrides) -> Event:
    base = {"run": "r1", "round": 1, "actor": "boss", "event": EventType.HIRED}
    return Event(**(base | overrides))


def sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


@pytest.fixture
def path(tmp_path):
    return tmp_path / "run" / "ledger.jsonl"


def write_all(path, n):
    with LedgerWriter(path) as w:
        for i in range(n):
            w.append(ev(round=i + 1, data={"n": i}))


def lines_of(path) -> list[bytes]:
    return path.read_bytes().split(b"\n")[:-1]


def put(path, lines: list[bytes]) -> None:
    path.write_bytes(b"".join(line + b"\n" for line in lines))


def test_the_first_line_follows_the_genesis_value_and_each_line_the_one_before(path):
    write_all(path, 4)
    lines = lines_of(path)
    prevs = [json.loads(line)["prev"] for line in lines]
    assert prevs[0] == GENESIS == "0" * 64
    assert prevs[1:] == [sha(line) for line in lines[:-1]]
    assert len(read_events(path)) == 4


def test_a_line_without_the_chain_has_no_prev_key_at_all():
    assert "prev" not in json.loads(ev().to_json())


def test_a_reopened_writer_continues_from_the_files_real_last_line(path):
    write_all(path, 2)
    with LedgerWriter(path) as w:
        w.append(ev(round=9))
    lines = lines_of(path)
    assert json.loads(lines[2])["prev"] == sha(lines[1])
    assert [e.round for e in read_events(path)] == [1, 2, 9]


def test_appends_from_several_threads_still_form_one_chain(path):
    with LedgerWriter(path) as w:

        def work(k):
            for i in range(25):
                w.append(ev(round=k, data={"i": i}))

        threads = [threading.Thread(target=work, args=(k,)) for k in range(1, 7)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert len(read_events(path)) == 150


def test_a_writer_that_is_not_the_only_one_breaks_the_chain_visibly(path):
    write_all(path, 2)
    with LedgerWriter(path) as w:
        with path.open("ab") as raw:  # someone who ignores the advisory lock
            raw.write((ev(round=7).to_json() + "\n").encode())
        w.append(ev(round=3))
    with pytest.raises(LedgerCorruptError, match=r":3: "):
        read_events(path)


def test_an_event_equal_to_another_stays_equal_wherever_it_sits(path):
    write_all(path, 2)
    first, second = read_events(path)
    assert first.prev == GENESIS and second.prev is not None
    assert first == ev(round=1, data={"n": 0}, ts=first.ts)


def test_a_prev_that_is_not_a_hash_is_refused():
    for bad in ("", "0" * 63, "g" * 64, "A" * 64, 5, None):
        line = json.loads(ev().to_json()) | {"prev": bad}
        with pytest.raises(ValueError):
            Event.from_json(json.dumps(line))
    with pytest.raises(ValueError):
        ev(prev="not a hash")


# --- older ledgers ---------------------------------------------------------------------------


def test_a_ledger_written_before_the_chain_still_loads(path):
    path.parent.mkdir(parents=True)
    put(path, [ev(round=n).to_json().encode() for n in (1, 2, 3)])
    assert [e.round for e in read_events(path)] == [1, 2, 3]
    assert all(e.prev is None for e in read_events(path))


def test_an_older_ledger_resumed_by_the_new_writer_is_anchored_to_its_last_old_line(path):
    path.parent.mkdir(parents=True)
    old = [ev(round=n).to_json().encode() for n in (1, 2)]
    put(path, old)
    with LedgerWriter(path) as w:
        w.append(ev(round=3))
        w.append(ev(round=4))
    lines = lines_of(path)
    assert json.loads(lines[2])["prev"] == sha(old[-1])
    assert [e.round for e in read_events(path)] == [1, 2, 3, 4]
    # the anchor is checked: change the old line the first chained line points at
    lines[1] = lines[1].replace(b'"round": 2', b'"round": 5')
    put(path, lines)
    with pytest.raises(LedgerCorruptError, match=r":3: .*chain"):
        read_events(path)


def test_lines_without_prev_after_lines_with_it_are_refused_and_named(path):
    write_all(path, 3)
    lines = lines_of(path)
    lines.append(ev(round=4).to_json().encode())  # an unchained line after the chain began
    put(path, lines)
    with pytest.raises(LedgerCorruptError, match=r":4: no `prev`"):
        read_events(path)


def test_a_chain_stripped_from_the_middle_of_a_ledger_is_refused(path):
    write_all(path, 4)
    lines = lines_of(path)
    plain = json.loads(lines[1])
    del plain["prev"]
    lines[1] = json.dumps(plain, sort_keys=True).encode()
    put(path, lines)
    with pytest.raises(LedgerCorruptError, match=r":2: no `prev`"):
        read_events(path)


def test_accepted_risk_a_ledger_with_every_prev_removed_loads_as_an_older_one(path):
    # Whoever can rewrite the whole file can also remove the chain; see docs/THREAT_MODEL.md T29.
    write_all(path, 3)
    stripped = []
    for line in lines_of(path):
        raw = json.loads(line)
        del raw["prev"]
        stripped.append(json.dumps(raw, sort_keys=True).encode())
    put(path, stripped)
    assert [e.round for e in read_events(path)] == [1, 2, 3]


def test_accepted_risk_trailing_lines_can_be_dropped_without_the_chain_noticing(path):
    write_all(path, 4)
    put(path, lines_of(path)[:2])
    assert len(read_events(path)) == 2


def test_accepted_risk_the_last_line_is_unprotected_until_another_follows(path):
    write_all(path, 3)
    lines = lines_of(path)
    lines[-1] = lines[-1].replace(b'"n": 2', b'"n": 7')  # still a valid line, nothing after it
    put(path, lines)
    assert read_events(path)[-1].data == {"n": 7}


# --- repair ----------------------------------------------------------------------------------


def test_repair_cuts_a_torn_last_line_and_the_chain_continues_from_the_new_last_line(path):
    write_all(path, 3)
    lines = lines_of(path)
    path.write_bytes(b"".join(line + b"\n" for line in lines[:2]) + lines[2][:30])
    assert repair_torn_tail(path) is not None
    assert [e.round for e in read_events(path)] == [1, 2]
    with LedgerWriter(path) as w:
        w.append(ev(round=3, data={"n": 2}))
    assert [e.round for e in read_events(path)] == [1, 2, 3]
    assert json.loads(lines_of(path)[2])["prev"] == sha(lines[1])


def test_a_torn_last_line_still_fails_closed_without_repair(path):
    write_all(path, 3)
    path.write_bytes(path.read_bytes()[:-15])
    with pytest.raises(LedgerCorruptError):
        read_events(path)


def test_repair_leaves_a_chain_broken_earlier_for_read_events_to_name(path):
    write_all(path, 4)
    lines = lines_of(path)
    lines[1] = lines[1].replace(b'"n": 1', b'"n": 9')
    path.write_bytes(b"".join(line + b"\n" for line in lines[:3]) + lines[3][:30])
    repair_torn_tail(path)
    with pytest.raises(LedgerCorruptError, match=r":3: .*chain"):
        read_events(path)


# --- fuzz: seeded, so a failure reproduces ----------------------------------------------------

SEEDS = range(8)


def chain_of(path, n=6):
    write_all(path, n)
    return lines_of(path)


def detected(path, lines) -> bool:
    put(path, lines)
    try:
        read_events(path)
    except LedgerCorruptError:
        return True
    return False


@pytest.mark.parametrize("seed", SEEDS)
def test_any_single_byte_flip_before_the_last_line_is_detected(path, seed):
    lines = chain_of(path)
    original = b"\n".join(lines)
    rng = random.Random(seed)
    last_starts_at = len(original) - len(lines[-1])
    for _ in range(300):
        i = rng.randrange(last_starts_at)  # every byte of lines 1..n-1 and their newlines
        mutated = bytearray(original)
        mutated[i] ^= rng.choice([0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80])
        path.write_bytes(bytes(mutated) + b"\n")
        with pytest.raises(LedgerCorruptError):
            read_events(path)


def test_every_byte_of_every_line_but_the_last_is_covered_by_some_flip(path):
    lines = chain_of(path, 4)
    original = b"\n".join(lines)
    for i in range(len(original) - len(lines[-1])):
        mutated = bytearray(original)
        mutated[i] ^= 0x01
        path.write_bytes(bytes(mutated) + b"\n")
        with pytest.raises(LedgerCorruptError):
            read_events(path)


@pytest.mark.parametrize("seed", SEEDS)
def test_any_flip_in_the_last_line_is_detected_unless_it_is_still_a_valid_event(path, seed):
    lines = chain_of(path)
    rng = random.Random(seed)
    for _ in range(200):
        mutated = bytearray(lines[-1])
        mutated[rng.randrange(len(mutated))] ^= rng.choice([0x01, 0x04, 0x20, 0x80])
        if detected(path, [*lines[:-1], bytes(mutated)]):
            continue
        # survived: it must be a line that parses, changes nothing the chain can see before it
        assert len(read_events(path)) == len(lines)


@pytest.mark.parametrize("seed", SEEDS)
def test_any_deleted_line_but_the_last_is_detected(path, seed):
    lines = chain_of(path)
    for i in range(len(lines) - 1):
        assert detected(path, lines[:i] + lines[i + 1 :]), f"line {i + 1} deleted"


def test_any_inserted_line_is_detected(path):
    lines = chain_of(path)
    plain = ev(round=9).to_json().encode()
    forged_prev = json.dumps(
        json.loads(ev(round=9).to_json()) | {"prev": "f" * 64}, sort_keys=True
    ).encode()
    duplicate = lines[2]
    for extra in (plain, forged_prev, duplicate):
        for i in range(len(lines)):  # before every line, including the first
            assert detected(path, [*lines[:i], extra, *lines[i:]]), f"{extra[:20]!r} at {i}"


@pytest.mark.parametrize("seed", SEEDS)
def test_any_reordering_is_detected(path, seed):
    lines = chain_of(path)
    rng = random.Random(seed)
    for _ in range(100):
        shuffled = lines[:]
        rng.shuffle(shuffled)
        if shuffled != lines:
            assert detected(path, shuffled)
    for i in range(len(lines) - 1):  # every adjacent swap
        swapped = lines[:]
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        assert detected(path, swapped)


def test_a_line_copied_from_another_ledger_is_detected(path, tmp_path):
    lines = chain_of(path)
    other = tmp_path / "other.jsonl"
    foreign = chain_of(other, 3)
    assert detected(path, [*lines[:3], foreign[1], *lines[3:]])


def test_the_first_line_deleted_is_detected_by_the_genesis_value(path):
    lines = chain_of(path, 3)
    assert detected(path, lines[1:])
