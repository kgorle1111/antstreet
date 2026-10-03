from log import WriteAheadLog
from store import KVStore


def test_delete_present_key(tmp_path):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    assert store.delete("a") is True
    assert "a" not in store
    assert store.get("a") is None
    assert len(store) == 0


def test_delete_absent_key_returns_false_and_logs_nothing(tmp_path):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    assert store.delete("ghost") is False
    assert log.replay() == []
    store.set("a", "1")
    assert store.delete("ghost") is False
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert log.replay() == [("set", "a", "1"), ("delete", "a", None)]


def test_delete_then_set_again(tmp_path):
    store = KVStore(WriteAheadLog(tmp_path / "db.log"))
    store.set("a", "1")
    store.delete("a")
    store.set("a", "2")
    assert store.get("a") == "2"
    assert store.keys() == ["a"]


def test_delete_survives_reopen(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    store.set("a", "1")
    store.set("b", "2")
    store.delete("a")
    again = KVStore(WriteAheadLog(path))
    assert again.keys() == ["b"]
    assert "a" not in again
