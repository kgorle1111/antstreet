from log import WriteAheadLog
from store import KVStore


def make(tmp_path):
    return KVStore(WriteAheadLog(tmp_path / "db.log"))


def test_empty_store(tmp_path):
    store = make(tmp_path)
    assert len(store) == 0
    assert store.keys() == []
    assert store.get("a") is None
    assert store.get("a", "d") == "d"
    assert "a" not in store


def test_set_and_get(tmp_path):
    store = make(tmp_path)
    store.set("a", "1")
    store.set("b", "2")
    assert store.get("a") == "1"
    assert store.get("b") == "2"
    assert len(store) == 2
    assert "a" in store and "c" not in store


def test_overwrite_keeps_one_entry(tmp_path):
    store = make(tmp_path)
    store.set("a", "1")
    store.set("a", "2")
    assert store.get("a") == "2"
    assert len(store) == 1


def test_empty_string_is_a_real_value(tmp_path):
    store = make(tmp_path)
    store.set("a", "")
    assert store.get("a", "default") == ""
    assert "a" in store
    assert len(store) == 1


def test_keys_sorted_and_a_copy(tmp_path):
    store = make(tmp_path)
    for key in ["b", "a", "C", "ab"]:
        store.set(key, "x")
    keys = store.keys()
    assert keys == ["C", "a", "ab", "b"]
    keys.clear()
    assert store.keys() == ["C", "a", "ab", "b"]
