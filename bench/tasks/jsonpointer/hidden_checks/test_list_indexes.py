import pytest
from jsonpointer import resolve

ITEMS = list("abcdefghijk")  # 11 elements, so "10" is the last valid index
MIXED = {"0": "zero", "01": "oh-one", "-": "dash"}


def test_valid_indexes():
    assert resolve(ITEMS, "/0") == "a"
    assert resolve(ITEMS, "/1") == "b"
    assert resolve(ITEMS, "/10") == "k"


def test_zero_alone_is_valid_but_not_with_leading_zeros():
    assert resolve([7], "/0") == 7
    for bad in ("/00", "/01", "/007"):
        with pytest.raises(KeyError):
            resolve(ITEMS, bad)


@pytest.mark.parametrize("token", ["-1", "+1", " 1", "1 ", "1_0", "1.0", "1e0", "0x1", "a", ""])
def test_non_index_tokens_raise_key_error(token):
    with pytest.raises(KeyError):
        resolve(ITEMS, "/" + token)


@pytest.mark.parametrize("token", ["١", "１", "²", "१"])
def test_non_ascii_digits_are_not_indexes(token):
    with pytest.raises(KeyError):
        resolve(ITEMS, "/" + token)


@pytest.mark.parametrize("token", ["11", "12", "100", "99999999999999999999"])
def test_out_of_range_raises_key_error(token):
    with pytest.raises(KeyError):
        resolve(ITEMS, "/" + token)


def test_dash_is_not_resolvable():
    with pytest.raises(KeyError):
        resolve(ITEMS, "/-")
    with pytest.raises(KeyError):
        resolve([[1]], "/-/0")


def test_empty_list_has_no_index_zero():
    with pytest.raises(KeyError):
        resolve([], "/0")


def test_digit_tokens_and_dash_are_plain_keys_on_dicts():
    assert resolve(MIXED, "/0") == "zero"
    assert resolve(MIXED, "/01") == "oh-one"
    assert resolve(MIXED, "/-") == "dash"


def test_an_index_never_finds_a_dict_key_by_position():
    with pytest.raises(KeyError):
        resolve({"a": 1}, "/0")
