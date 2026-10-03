import pytest
from log import WriteAheadLog
from store import KVStore


@pytest.mark.parametrize("key", ["", None, 5, b"a", ("a",)])
def test_set_rejects_bad_keys(tmp_path, key):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    with pytest.raises(ValueError):
        store.set(key, "v")
    assert len(store) == 0
    assert log.replay() == []


@pytest.mark.parametrize("value", [None, 5, b"v", ["v"]])
def test_set_rejects_non_str_values(tmp_path, value):
    log = WriteAheadLog(tmp_path / "db.log")
    store = KVStore(log)
    with pytest.raises(ValueError):
        store.set("k", value)
    assert "k" not in store
    assert log.replay() == []


@pytest.mark.parametrize("key", ["", None, 5])
def test_delete_rejects_bad_keys(tmp_path, key):
    store = KVStore(WriteAheadLog(tmp_path / "db.log"))
    with pytest.raises(ValueError):
        store.delete(key)


def test_log_append_validates_and_writes_nothing(tmp_path):
    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    for args in [
        ("upsert", "a", "1"),
        ("set", "", "1"),
        ("set", 3, "1"),
        ("set", "a", None),
        ("set", "a", 1),
        ("delete", "", None),
        ("delete", None, None),
        ("SET", "a", "1"),
    ]:
        with pytest.raises(ValueError):
            log.append(*args)
    assert not path.exists()
    assert log.replay() == []


def test_log_append_set_without_a_value_is_invalid(tmp_path):
    with pytest.raises(ValueError):
        WriteAheadLog(tmp_path / "db.log").append("set", "a")


def test_log_rewrite_validates_before_touching_the_file(tmp_path):
    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    log.append("set", "a", "1")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        log.rewrite([("set", "b", "2"), ("set", "", "3")])
    with pytest.raises(ValueError):
        log.rewrite([("nope", "b", "2")])
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["db.log"]


def test_log_rewrite_replaces_and_normalises_deletes(tmp_path):
    path = tmp_path / "db.log"
    log = WriteAheadLog(path)
    log.append("set", "old", "1")
    log.rewrite([("set", "a", "1"), ("delete", "a", "ignored"), ("set", "b", "")])
    assert log.replay() == [("set", "a", "1"), ("delete", "a", None), ("set", "b", "")]
    assert path.read_bytes().count(b"\n") == 3
    assert [p.name for p in tmp_path.iterdir()] == ["db.log"]
    log.rewrite([])
    assert path.read_bytes() == b""
