from log import WriteAheadLog
from store import KVStore


def test_compact_leaves_one_set_per_live_key_sorted(tmp_path):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("b", "1")
    store.set("a", "1")
    store.set("b", "2")
    store.set("gone", "x")
    store.delete("gone")
    store.compact()
    assert log.replay() == [("set", "a", "1"), ("set", "b", "2")]


def test_compacted_log_rebuilds_the_same_store(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    for i in range(20):
        store.set(f"k{i % 5}", str(i))
    store.delete("k0")
    store.set("empty", "")
    live = store.keys()
    before = {k: store.get(k) for k in live}
    store.compact()
    again = KVStore(WriteAheadLog(path))
    reopened = again.keys()
    assert {k: again.get(k) for k in reopened} == before
    assert len(WriteAheadLog(path).replay()) == len(before)


def test_compact_empty_store_leaves_an_empty_file(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    store.set("a", "1")
    store.delete("a")
    store.compact()
    assert path.read_bytes() == b""
    assert WriteAheadLog(path).replay() == []


def test_compact_before_any_write_creates_an_empty_log(tmp_path):
    path = tmp_path / "db.log"
    KVStore(WriteAheadLog(path)).compact()
    assert path.read_bytes() == b""


def test_store_keeps_working_after_compact(tmp_path):
    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    store = KVStore(log)
    store.set("a", "1")
    store.set("a", "2")
    store.compact()
    store.set("b", "3")
    store.delete("a")
    assert log.replay() == [("set", "a", "2"), ("set", "b", "3"), ("delete", "a", None)]
    assert KVStore(WriteAheadLog(path)).keys() == ["b"]


def test_compact_removes_a_torn_tail(tmp_path):
    path = tmp_path / "db.log"
    path.write_text('{"op": "set", "key": "a", "value": "1"}\n{"op": "se', encoding="utf-8")
    store = KVStore(WriteAheadLog(path))
    store.compact()
    assert path.read_bytes().endswith(b"\n")
    assert path.read_text(encoding="utf-8").count("\n") == 1


def test_compact_stores_through_rewrite_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    store.set("a", "1")
    store.compact()
    store.compact()
    assert [p.name for p in tmp_path.iterdir()] == ["db.log"]
