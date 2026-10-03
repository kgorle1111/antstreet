import pytest
from log import WriteAheadLog
from store import KVStore


class FailingLog(WriteAheadLog):
    def __init__(self, path):
        super().__init__(path)
        self.fail = False
        self.calls = []

    def append(self, op, key, value=None):
        self.calls.append((op, key, value))
        if self.fail:
            raise OSError("disk full")
        super().append(op, key, value)


def test_failed_set_leaves_store_unchanged(tmp_path):
    log = FailingLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    log.fail = True
    with pytest.raises(OSError):
        store.set("a", "2")
    with pytest.raises(OSError):
        store.set("b", "3")
    assert store.get("a") == "1"
    assert "b" not in store
    assert len(store) == 1


def test_failed_delete_keeps_the_key(tmp_path):
    log = FailingLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    log.fail = True
    with pytest.raises(OSError):
        store.delete("a")
    assert store.get("a") == "1"
    assert store.keys() == ["a"]


def test_the_store_calls_append_with_the_documented_arguments(tmp_path):
    log = FailingLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    store.delete("a")
    store.delete("a")
    assert log.calls == [("set", "a", "1"), ("delete", "a", None)]


def test_store_works_with_any_object_that_has_the_log_methods():
    class Memory:
        def __init__(self):
            self.records = []

        def append(self, op, key, value=None):
            self.records.append((op, key, value if op == "set" else None))

        def replay(self):
            return list(self.records)

        def rewrite(self, records):
            self.records = list(records)

    memory = Memory()
    store = KVStore(memory)
    store.set("x", "1")
    store.set("y", "2")
    store.delete("x")
    assert KVStore(memory).keys() == ["y"]
    store.compact()
    assert memory.records == [("set", "y", "2")]


def test_failed_compact_leaves_store_unchanged(tmp_path):
    class BadRewrite(WriteAheadLog):
        def rewrite(self, records):
            raise OSError("no space")

    log = BadRewrite(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    with pytest.raises(OSError):
        store.compact()
    assert store.get("a") == "1"
    assert log.replay() == [("set", "a", "1")]
