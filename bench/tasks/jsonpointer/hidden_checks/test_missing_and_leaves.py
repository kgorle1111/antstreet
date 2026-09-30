import pytest
from jsonpointer import resolve


def test_missing_key_raises_key_error():
    with pytest.raises(KeyError):
        resolve({"a": 1}, "/b")
    with pytest.raises(KeyError):
        resolve({"a": {"b": 1}}, "/a/c")
    with pytest.raises(KeyError):
        resolve({}, "/a/b/c")


def test_keys_are_case_sensitive_and_exact():
    with pytest.raises(KeyError):
        resolve({"a": 1}, "/A")
    with pytest.raises(KeyError):
        resolve({"a": 1}, "/a ")
    with pytest.raises(KeyError):
        resolve({"a": 1}, "/")


def test_none_value_is_present_but_cannot_be_descended_into():
    assert resolve({"a": None}, "/a") is None
    with pytest.raises(KeyError):
        resolve({"a": None}, "/b")
    with pytest.raises(KeyError):
        resolve({"a": None}, "/a/b")


@pytest.mark.parametrize("leaf", [5, 1.5, True, False, None, "text", ""])
def test_descending_into_a_leaf_raises_key_error(leaf):
    for pointer in ("/a/b", "/a/0", "/a/-", "/a/"):
        with pytest.raises(KeyError):
            resolve({"a": leaf}, pointer)


def test_strings_are_not_indexed_like_lists():
    with pytest.raises(KeyError):
        resolve({"s": "hello"}, "/s/0")
    with pytest.raises(KeyError):
        resolve("hello", "/0")


def test_a_leaf_document_only_answers_the_empty_pointer():
    assert resolve(7, "") == 7
    with pytest.raises(KeyError):
        resolve(7, "/a")
    with pytest.raises(KeyError):
        resolve(None, "/")
