import time

import pytest
from rlecodec import decode


def test_the_default_limit_is_one_million_characters():
    assert len(decode("1000000a")) == 1_000_000
    with pytest.raises(ValueError):
        decode("1000001a")


@pytest.mark.parametrize(
    "encoded", ["99999999999999a", "2000000a", "1000001a", "999999999999999999999999a"]
)
def test_a_huge_count_raises_value_error_quickly_and_without_building_the_text(encoded):
    started = time.monotonic()
    with pytest.raises(ValueError):
        decode(encoded)
    assert time.monotonic() - started < 2.0


def test_a_count_of_thousands_of_digits_raises_value_error():
    with pytest.raises(ValueError):
        decode("9" * 5000 + "a")
    with pytest.raises(ValueError):
        decode("1" + "0" * 20000 + "a")


def test_the_limit_applies_to_the_total_of_all_tokens():
    with pytest.raises(ValueError):
        decode("600000a600000b")
    assert len(decode("500000a500000b")) == 1_000_000
    with pytest.raises(ValueError):
        decode("500000a500000b1c")
    with pytest.raises(ValueError):
        decode("1a" * 101, max_output=100)


def test_a_custom_limit():
    assert decode("5a", max_output=5) == "aaaaa"
    assert decode("5a", 5) == "aaaaa"
    assert decode("2a3b", max_output=5) == "aabbb"
    with pytest.raises(ValueError):
        decode("6a", max_output=5)
    with pytest.raises(ValueError):
        decode("2a4b", max_output=5)
    with pytest.raises(ValueError):
        decode("5a1b", max_output=5)


def test_a_limit_of_zero_allows_only_the_empty_text():
    assert decode("", max_output=0) == ""
    with pytest.raises(ValueError):
        decode("1a", max_output=0)


def test_a_larger_limit_allows_larger_output():
    assert len(decode("3000000a", max_output=3_000_000)) == 3_000_000
    assert len(decode("1500000a1500000b", max_output=3_000_000)) == 3_000_000


def test_the_limit_is_on_characters_not_tokens_or_bytes():
    assert decode("3\u00e9", max_output=3) == "\u00e9\u00e9\u00e9"
    assert decode("2\U0001f600", max_output=2) == "\U0001f600\U0001f600"
    assert decode("1a" * 10, max_output=10) == "a" * 10


def test_an_invalid_text_is_still_invalid_under_a_large_limit():
    with pytest.raises(ValueError):
        decode("3a0b", max_output=10**9)


@pytest.mark.parametrize("limit", [-1, -100, -(10**9)])
def test_a_negative_limit_raises_value_error(limit):
    with pytest.raises(ValueError):
        decode("1a", max_output=limit)
    with pytest.raises(ValueError):
        decode("", limit)


@pytest.mark.parametrize("limit", ["10", None, 10.0, 1e6, True, False, b"10", [10]])
def test_a_limit_that_is_not_an_int_raises_type_error(limit):
    with pytest.raises(TypeError):
        decode("1a", max_output=limit)
    with pytest.raises(TypeError):
        decode("1a", limit)
