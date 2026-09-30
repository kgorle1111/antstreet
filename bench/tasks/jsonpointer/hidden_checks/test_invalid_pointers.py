import pytest
from jsonpointer import resolve, set_value

DOC = {"a": {"b": [1, 2]}}


@pytest.mark.parametrize("pointer", ["a", "a/b", "foo", " /a", "~0", "~1/a", "0", "#/a"])
def test_pointer_must_start_with_a_slash(pointer):
    with pytest.raises(ValueError):
        resolve(DOC, pointer)


@pytest.mark.parametrize(
    "pointer",
    ["/~", "/a~", "/~2", "/a~b", "/~~0", "/~ ", "/a/b~", "/~/a", "/a~/b", "/~00~"],
)
def test_bad_tilde_sequences_raise_value_error(pointer):
    with pytest.raises(ValueError):
        resolve(DOC, pointer)


def test_malformed_pointer_wins_over_missing_key():
    with pytest.raises(ValueError):
        resolve({}, "/missing/~")
    with pytest.raises(ValueError):
        resolve({}, "/missing/~2/x")
    with pytest.raises(ValueError):
        resolve(5, "/a~")


def test_malformed_pointer_wins_over_leaf_descent():
    with pytest.raises(ValueError):
        resolve({"a": 5}, "/a/b~")


@pytest.mark.parametrize("pointer", ["a", "/~", "/a~x", "/missing/~3"])
def test_set_value_rejects_malformed_pointers(pointer):
    with pytest.raises(ValueError):
        set_value(DOC, pointer, 1)


def test_valid_look_alikes_do_not_raise():
    assert resolve({"~": 1}, "/~0") == 1
    assert resolve({"/": 1}, "/~1") == 1
    assert resolve({"": 1}, "/") == 1
    assert resolve({"a b": 1}, "/a b") == 1
