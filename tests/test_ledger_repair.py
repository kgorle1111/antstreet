import pytest

from boss.ledger import (
    Event,
    EventType,
    LedgerCorruptError,
    LedgerLockedError,
    LedgerWriter,
    read_events,
    repair_torn_tail,
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


def torn_file(path, keep=2, cut=20):
    """A ledger with `keep` complete lines and a last line cut `cut` bytes in."""
    write_all(path, [ev(round=n + 1) for n in range(keep + 1)])
    lines = path.read_bytes().split(b"\n")[:-1]
    complete = b"".join(line + b"\n" for line in lines[:keep])
    path.write_bytes(complete + lines[keep][:cut])
    return complete, lines[keep][:cut].decode()


def test_appends_end_with_a_newline(path):
    write_all(path, [ev(), ev(round=2)])
    assert path.read_bytes().endswith(b"\n")


def test_repair_cuts_a_torn_last_line_and_returns_it(path):
    complete, torn = torn_file(path)
    with pytest.raises(LedgerCorruptError):
        read_events(path)
    assert repair_torn_tail(path) == torn
    assert path.read_bytes() == complete
    assert [e.round for e in read_events(path)] == [1, 2]


def test_repair_twice_is_a_no_op(path):
    torn_file(path)
    assert repair_torn_tail(path) is not None
    after = path.read_bytes()
    assert repair_torn_tail(path) is None
    assert path.read_bytes() == after


def test_repair_handles_a_tear_inside_a_multibyte_character(path):
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"v": 1, "note": "' + "é".encode()[:1])  # half of a two-byte character
    assert repair_torn_tail(path) is not None
    assert path.read_bytes() == b""


def test_repair_can_empty_a_file_whose_only_line_is_torn(path):
    torn_file(path, keep=0)
    assert repair_torn_tail(path) is not None
    assert path.read_bytes() == b""


@pytest.mark.parametrize("state", ["empty", "clean"])
def test_repair_ignores_a_file_with_nothing_torn(path, state):
    path.parent.mkdir(parents=True)
    if state == "empty":
        path.write_bytes(b"")
    else:
        write_all(path, [ev(), ev(round=2)])
    before = path.read_bytes()
    assert repair_torn_tail(path) is None
    assert path.read_bytes() == before


def test_repair_leaves_a_missing_file_missing(path):
    assert repair_torn_tail(path) is None
    assert not path.exists()


def test_repair_leaves_a_corrupt_last_line_that_ends_with_a_newline(path):
    write_all(path, [ev()])
    with path.open("ab") as fh:
        fh.write(b'{"v": 1, "run": \n')
    before = path.read_bytes()
    assert repair_torn_tail(path) is None
    assert path.read_bytes() == before


def test_repair_leaves_a_corrupt_middle_line_alone(path):
    write_all(path, [ev(), ev(round=2)])
    lines = path.read_bytes().split(b"\n")
    path.write_bytes(lines[0][:15] + b"\n" + lines[1][:30])  # bad middle, torn tail
    before = path.read_bytes()
    assert repair_torn_tail(path) is None
    assert path.read_bytes() == before


def test_repair_leaves_an_intact_last_line_that_only_lost_its_newline(path):
    write_all(path, [ev(), ev(round=2)])
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    before = path.read_bytes()
    assert repair_torn_tail(path) is None
    assert path.read_bytes() == before


def test_repair_is_refused_while_a_writer_holds_the_file(path):
    torn_file(path)
    before = path.read_bytes()
    with LedgerWriter(path), pytest.raises(LedgerLockedError):
        repair_torn_tail(path)
    assert path.read_bytes() == before


def test_a_writer_is_refused_while_repair_holds_the_file(path, monkeypatch):
    torn_file(path)
    seen = []
    real = Event.from_json

    def probe(line):
        if not seen:  # repair is mid-flight and holds the lock
            seen.append(True)
            with pytest.raises(LedgerLockedError), LedgerWriter(path):
                pass
        return real(line)

    monkeypatch.setattr(Event, "from_json", staticmethod(probe))
    assert repair_torn_tail(path) is not None
    assert seen
    monkeypatch.undo()
    with LedgerWriter(path) as w:  # the lock is released afterwards
        w.append(ev(round=9))
