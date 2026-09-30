import pytest
from jsonpointer import set_value


def test_empty_pointer_returns_the_value():
    new = {"z": 1}
    assert set_value({"a": 1}, "", new) is new
    assert set_value({"a": 1}, "", 5) == 5
    assert set_value([1], "", None) is None
    assert set_value(3, "", "x") == "x"


def test_replace_an_existing_dict_key():
    assert set_value({"a": 1, "b": 2}, "/a", 9) == {"a": 9, "b": 2}


def test_add_a_new_dict_key():
    assert set_value({"a": 1}, "/b", 2) == {"a": 1, "b": 2}
    assert set_value({}, "/a", None) == {"a": None}


def test_set_a_nested_value():
    doc = {"a": {"b": [1, {"c": 2}]}}
    assert set_value(doc, "/a/b/1/c", 3) == {"a": {"b": [1, {"c": 3}]}}
    assert set_value(doc, "/a/d", 4) == {"a": {"b": [1, {"c": 2}], "d": 4}}


def test_replace_a_list_element():
    assert set_value({"l": [1, 2, 3]}, "/l/1", 9) == {"l": [1, 9, 3]}
    assert set_value([1, 2, 3], "/0", 9) == [9, 2, 3]
    assert set_value([1, 2, 3], "/2", 9) == [1, 2, 9]


def test_dash_appends_to_a_list():
    assert set_value({"l": [1, 2]}, "/l/-", 3) == {"l": [1, 2, 3]}
    assert set_value([], "/-", "x") == ["x"]
    assert set_value([[1]], "/0/-", 2) == [[1, 2]]


def test_dash_is_an_ordinary_key_on_a_dict():
    assert set_value({}, "/-", 1) == {"-": 1}
    assert set_value({"-": 1}, "/-", 2) == {"-": 2}


def test_digit_tokens_are_ordinary_keys_on_a_dict():
    assert set_value({}, "/0", "x") == {"0": "x"}
    assert set_value({"a": {}}, "/a/01", "x") == {"a": {"01": "x"}}


def test_empty_key_and_container_values():
    assert set_value({}, "/", 1) == {"": 1}
    assert set_value({"a": 1}, "/a", {"b": [1]}) == {"a": {"b": [1]}}
    assert set_value({"a": 1}, "/a", None) == {"a": None}


def test_a_leaf_can_be_replaced_by_a_container_and_back():
    assert set_value({"a": 5}, "/a", []) == {"a": []}
    assert set_value({"a": {"b": 1}}, "/a", 5) == {"a": 5}


def test_nothing_is_ever_inserted_in_the_middle():
    result = set_value([1, 2, 3], "/1", 9)
    assert result == [1, 9, 3]
    assert len(result) == 3


def test_index_equal_to_length_is_out_of_range():
    with pytest.raises(KeyError):
        set_value([1, 2], "/2", 3)
    with pytest.raises(KeyError):
        set_value([], "/0", 1)
    with pytest.raises(KeyError):
        set_value({"l": [1]}, "/l/5", 1)
