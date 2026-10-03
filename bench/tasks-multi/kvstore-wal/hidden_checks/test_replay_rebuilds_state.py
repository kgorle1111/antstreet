from log import WriteAheadLog
from store import KVStore


def test_reopen_sees_the_same_data(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    store.set("a", "1")
    store.set("b", "2")
    store.set("a", "3")
    again = KVStore(WriteAheadLog(path))
    assert again.get("a") == "3"
    assert again.get("b") == "2"
    assert again.keys() == ["a", "b"]
    assert len(again) == 2


def test_replay_applies_a_hand_written_log_in_order(tmp_path):
    path = tmp_path / "db.log"
    path.write_text(
        '{"op": "set", "key": "a", "value": "1"}\n'
        '{"op": "delete", "key": "ghost", "value": null}\n'
        '{"op": "set", "key": "b", "value": "2"}\n'
        '{"op": "delete", "key": "a", "value": null}\n'
        '{"op": "set", "key": "a", "value": "again"}\n',
        encoding="utf-8",
    )
    log = WriteAheadLog(path)
    assert len(log.replay()) == 5
    store = KVStore(log)
    assert store.keys() == ["a", "b"]
    assert store.get("a") == "again"


def test_writes_after_reopen_extend_the_same_log(tmp_path):
    path = tmp_path / "db.log"
    first = KVStore(WriteAheadLog(path))
    first.set("a", "1")
    second = KVStore(WriteAheadLog(path))
    second.set("b", "2")
    second.delete("a")
    third = KVStore(WriteAheadLog(path))
    assert third.keys() == ["b"]
    assert WriteAheadLog(path).replay() == [
        ("set", "a", "1"),
        ("set", "b", "2"),
        ("delete", "a", None),
    ]


def test_missing_file_is_an_empty_log(tmp_path):
    log = WriteAheadLog(tmp_path / "nothing.log")
    assert log.replay() == []
    assert len(KVStore(log)) == 0


def test_special_characters_round_trip(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    pairs = {
        "multi\nline": 'tab\there\r\nand "quotes" and \\ backslash',
        "unicode-é中\U0001f600": "  line separator \x00 nul",
        " spaced key ": "  ",
    }
    for key, value in pairs.items():
        store.set(key, value)
    data = path.read_bytes()
    assert data.count(b"\n") == len(pairs)
    again = KVStore(WriteAheadLog(path))
    for key, value in pairs.items():
        assert again.get(key) == value
    assert len(again) == 3


def test_accepts_str_path_and_pathlike(tmp_path):
    as_str = str(tmp_path / "s.log")
    KVStore(WriteAheadLog(as_str)).set("a", "1")
    assert KVStore(WriteAheadLog(as_str)).get("a") == "1"
    KVStore(WriteAheadLog(tmp_path / "p.log")).set("b", "2")
    assert KVStore(WriteAheadLog(tmp_path / "p.log")).get("b") == "2"
