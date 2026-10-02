import pytest
from log import WriteAheadLog
from store import KVStore

GOOD = '{"op": "set", "key": "a", "value": "1"}\n'


def test_partial_last_line_is_ignored(tmp_path):
    path = tmp_path / "db.log"
    path.write_text(GOOD + '{"op": "set", "key": "b", "val', encoding="utf-8")
    log = WriteAheadLog(path)
    assert log.replay() == [("set", "a", "1")]
    store = KVStore(log)
    assert store.keys() == ["a"]


def test_complete_but_unterminated_last_line_is_still_ignored(tmp_path):
    path = tmp_path / "db.log"
    path.write_text(GOOD + '{"op": "set", "key": "b", "value": "2"}', encoding="utf-8")
    assert WriteAheadLog(path).replay() == [("set", "a", "1")]
    assert KVStore(WriteAheadLog(path)).keys() == ["a"]


def test_file_with_only_a_torn_line_is_empty(tmp_path):
    path = tmp_path / "db.log"
    path.write_text('{"op": "se', encoding="utf-8")
    assert WriteAheadLog(path).replay() == []
    assert len(KVStore(WriteAheadLog(path))) == 0


def test_replay_does_not_modify_the_file(tmp_path):
    path = tmp_path / "db.log"
    path.write_text(GOOD + '{"op": "set"', encoding="utf-8")
    before = path.read_bytes()
    WriteAheadLog(path).replay()
    KVStore(WriteAheadLog(path))
    assert path.read_bytes() == before


def test_a_torn_multibyte_character_at_the_tail_is_ignored(tmp_path):
    path = tmp_path / "db.log"
    path.write_bytes(GOOD.encode() + '{"op": "set", "key": "é'.encode()[:-1])
    assert WriteAheadLog(path).replay() == [("set", "a", "1")]


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all\n",
        "\n",
        "[]\n",
        '{"op": "set", "key": "a"}\n',
        '{"op": "set", "key": "a", "value": "1", "extra": 1}\n',
        '{"op": "upsert", "key": "a", "value": "1"}\n',
        '{"op": "set", "key": "", "value": "1"}\n',
        '{"op": "set", "key": 5, "value": "1"}\n',
        '{"op": "set", "key": "a", "value": null}\n',
        '{"op": "set", "key": "a", "value": 7}\n',
        '{"op": "delete", "key": "a", "value": "x"}\n',
    ],
)
def test_a_terminated_bad_line_is_corruption(tmp_path, bad):
    path = tmp_path / "db.log"
    path.write_text(GOOD + bad + GOOD, encoding="utf-8")
    with pytest.raises(ValueError):
        WriteAheadLog(path).replay()
    with pytest.raises(ValueError):
        KVStore(WriteAheadLog(path))


def test_a_terminated_bad_last_line_is_corruption_not_torn(tmp_path):
    path = tmp_path / "db.log"
    path.write_text(GOOD + "garbage\n", encoding="utf-8")
    with pytest.raises(ValueError):
        WriteAheadLog(path).replay()
