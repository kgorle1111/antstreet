import pytest
from jsonpointer import set_value


def test_missing_parent_raises_key_error():
    with pytest.raises(KeyError):
        set_value({}, "/a/b", 1)
    with pytest.raises(KeyError):
        set_value({"a": {}}, "/a/b/c", 1)
    with pytest.raises(KeyError):
        set_value({"l": []}, "/l/0/x", 1)


@pytest.mark.parametrize("leaf", [5, 1.5, True, None, "text", ""])
def test_leaf_parent_raises_key_error(leaf):
    with pytest.raises(KeyError):
        set_value({"a": leaf}, "/a/b", 1)
    with pytest.raises(KeyError):
        set_value({"a": leaf}, "/a/0", 1)
    with pytest.raises(KeyError):
        set_value({"a": leaf}, "/a/-", 1)


def test_leaf_document_only_accepts_the_empty_pointer():
    assert set_value(5, "", 6) == 6
    with pytest.raises(KeyError):
        set_value(5, "/a", 1)
    with pytest.raises(KeyError):
        set_value("hello", "/0", "j")


@pytest.mark.parametrize("token", ["01", "-1", "+1", "a", "1.0", " 1", "١", ""])
def test_bad_list_tokens_raise_key_error(token):
    with pytest.raises(KeyError):
        set_value([1, 2, 3], "/" + token, 9)


def test_dash_before_the_last_token_does_not_resolve():
    with pytest.raises(KeyError):
        set_value([[1]], "/-/0", 9)
    with pytest.raises(KeyError):
        set_value({"l": [{"a": 1}]}, "/l/-/a", 9)


def test_out_of_range_index_in_the_middle_raises_key_error():
    with pytest.raises(KeyError):
        set_value({"l": [{"a": 1}]}, "/l/1/a", 9)


def test_malformed_pointer_raises_value_error_not_key_error():
    with pytest.raises(ValueError):
        set_value({}, "no-slash", 1)
    with pytest.raises(ValueError):
        set_value({}, "/missing/~9", 1)
    with pytest.raises(ValueError):
        set_value([], "/-~", 1)
