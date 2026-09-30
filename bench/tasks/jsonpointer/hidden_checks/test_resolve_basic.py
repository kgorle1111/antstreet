from jsonpointer import resolve

DOC = {
    "foo": ["bar", "baz"],
    "": 0,
    "a/b": 1,
    "c%d": 2,
    "e^f": 3,
    "g|h": 4,
    "i\\j": 5,
    'k"l': 6,
    " ": 7,
    "m~n": 8,
}


def test_empty_pointer_is_the_whole_document():
    assert resolve(DOC, "") is DOC
    assert resolve([1, 2], "") == [1, 2]
    assert resolve(5, "") == 5


def test_rfc_examples():
    assert resolve(DOC, "/foo") == ["bar", "baz"]
    assert resolve(DOC, "/foo/0") == "bar"
    assert resolve(DOC, "/") == 0
    assert resolve(DOC, "/a~1b") == 1
    assert resolve(DOC, "/c%d") == 2
    assert resolve(DOC, "/e^f") == 3
    assert resolve(DOC, "/g|h") == 4
    assert resolve(DOC, "/i\\j") == 5
    assert resolve(DOC, '/k"l') == 6
    assert resolve(DOC, "/ ") == 7
    assert resolve(DOC, "/m~0n") == 8


def test_nested_dicts_and_lists():
    doc = {"a": {"b": [10, {"c": [None, 5]}]}}
    assert resolve(doc, "/a/b/1/c/1") == 5
    assert resolve(doc, "/a/b/0") == 10
    assert resolve(doc, "/a") == {"b": [10, {"c": [None, 5]}]}


def test_root_can_be_a_list():
    assert resolve([[1, 2], [3]], "/1/0") == 3


def test_resolve_returns_the_object_itself():
    doc = {"a": {"b": [1]}}
    assert resolve(doc, "/a") is doc["a"]
    assert resolve(doc, "/a/b") is doc["a"]["b"]


def test_empty_keys_are_ordinary_keys():
    assert resolve({"": {"": 2}}, "//") == 2
    assert resolve({"a": {"": 3}}, "/a/") == 3


def test_none_and_falsy_values_are_found():
    doc = {"n": None, "z": 0, "f": False, "s": "", "l": []}
    assert resolve(doc, "/n") is None
    assert resolve(doc, "/z") == 0
    assert resolve(doc, "/f") is False
    assert resolve(doc, "/s") == ""
    assert resolve(doc, "/l") == []
