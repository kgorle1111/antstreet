import pytest
from rlecodec import decode


@pytest.mark.parametrize(
    ("encoded", "text"),
    [
        ("", ""),
        ("1a", "a"),
        ("3a1b2c", "aaabcc"),
        ("12W1B12W3B24W1B14W", "W" * 12 + "B" + "W" * 12 + "BBB" + "W" * 24 + "B" + "W" * 14),
        ("2\\1", "11"),
        ("1\\\\", "\\"),
        ("3\\\\", "\\\\\\"),
        ("1a1\\\\1b", "a\\b"),
        ("1\\01\\11\\2", "012"),
        ("10x", "x" * 10),
        ("100x", "x" * 100),
        ("123x", "x" * 123),
        ("1000a1b", "a" * 1000 + "b"),
        ("1 ", " "),
        ("2\n", "\n\n"),
        ("1a2\n", "a\n\n"),
        ("3\u00e9", "\u00e9\u00e9\u00e9"),
        ("2\U0001f600", "\U0001f600\U0001f600"),
    ],
)
def test_known_decodings(encoded, text):
    assert decode(encoded) == text


@pytest.mark.parametrize(
    ("encoded", "text"),
    [
        ("1a1a", "aa"),
        ("2a3a", "aaaaa"),
        ("1a1a1a", "aaa"),
        ("3a3a", "aaaaaa"),
        ("1\\11\\1", "11"),
        ("2a1b1b", "aabb"),
    ],
)
def test_tokens_that_encode_would_not_write_are_accepted(encoded, text):
    assert decode(encoded) == text


def test_a_count_may_have_several_digits():
    assert decode("10a") == "a" * 10
    assert decode("11a") == "a" * 11
    assert decode("99a") == "a" * 99
    assert decode("20a30b") == "a" * 20 + "b" * 30
    assert decode("100000z") == "z" * 100000
    assert decode("1234a") == "a" * 1234
    assert decode("101a") == "a" * 101


def test_the_digits_of_a_count_are_not_a_unit_even_when_they_look_like_one():
    assert decode("12a") == "a" * 12
    assert decode("51a") == "a" * 51


def test_an_escaped_digit_after_a_count_is_the_unit():
    assert decode("5\\5") == "55555"
    assert decode("12\\3") == "3" * 12
    assert decode("1\\12\\2") == "122"


def test_a_digit_unit_followed_by_more_tokens():
    assert decode("2\\11a") == "11a"
    assert decode("1a2\\2") == "a22"


def test_non_ascii_digits_are_ordinary_units():
    assert decode("3\u0663") == "\u0663" * 3
    assert decode("2\uff11") == "\uff11" * 2


def test_the_result_is_a_str():
    assert type(decode("")) is str
    assert type(decode("2a")) is str
