import pytest
from urlquery import build_query


@pytest.mark.parametrize("key", [1, None, b"a", 2.5, ("a",)])
def test_non_string_key_raises(key):
    with pytest.raises(ValueError):
        build_query({key: "v"})


def test_empty_key_raises():
    with pytest.raises(ValueError):
        build_query({"": "v"})
    with pytest.raises(ValueError):
        build_query({"a": "1", "": ["x"]})


@pytest.mark.parametrize("value", [1, None, 2.5, b"x", True, {"a": "b"}, {"x"}])
def test_value_of_the_wrong_type_raises(value):
    with pytest.raises(ValueError):
        build_query({"a": value})


@pytest.mark.parametrize("items", [[1], ["a", None], ("a", b"b"), [["x"]], ["ok", 3, "ok"]])
def test_non_string_list_item_raises(items):
    with pytest.raises(ValueError):
        build_query({"a": items})


@pytest.mark.parametrize("bad", [None, [], [("a", "1")], "a=1", 5, ("a",)])
def test_non_dict_argument_raises(bad):
    with pytest.raises(ValueError):
        build_query(bad)
