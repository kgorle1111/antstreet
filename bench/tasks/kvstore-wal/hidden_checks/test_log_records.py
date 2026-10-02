from log import WriteAheadLog
from store import KVStore


def test_every_set_and_delete_is_one_record_in_order(tmp_path):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    store.set("a", "2")
    store.set("b", "")
    store.delete("a")
    assert log.replay() == [
        ("set", "a", "1"),
        ("set", "a", "2"),
        ("set", "b", ""),
        ("delete", "a", None),
    ]


def test_same_value_set_is_still_logged(tmp_path):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    store.set("a", "1")
    store.set("a", "1")
    assert log.replay() == [("set", "a", "1"), ("set", "a", "1")]


def test_reads_do_not_touch_the_log(tmp_path):
    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    store = KVStore(log)
    store.set("a", "1")
    before = path.read_bytes()
    store.get("a")
    store.get("zz")
    store.keys()
    len(store)
    assert "a" in store
    assert path.read_bytes() == before


def test_file_format_is_one_json_line_per_record(tmp_path):
    import json

    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    log.append("set", "k", "v")
    log.append("delete", "k", "ignored")
    data = path.read_bytes()
    assert data.endswith(b"\n")
    lines = data.decode("utf-8").split("\n")[:-1]
    assert [json.loads(line) for line in lines] == [
        {"op": "set", "key": "k", "value": "v"},
        {"op": "delete", "key": "k", "value": None},
    ]
    assert log.replay() == [("set", "k", "v"), ("delete", "k", None)]


def test_append_only_never_rewrites_earlier_lines(tmp_path):
    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    log.append("set", "a", "1")
    first = path.read_bytes()
    log.append("set", "b", "2")
    assert path.read_bytes().startswith(first)
    assert len(path.read_bytes()) > len(first)


def test_constructing_a_log_touches_nothing(tmp_path):
    path = tmp_path / "db.log"
    store = KVStore(WriteAheadLog(path))
    assert not path.exists()
    assert len(store) == 0
    assert list(tmp_path.iterdir()) == []
