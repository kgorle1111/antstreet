import pytest
from rlecodec import decode


@pytest.mark.parametrize(
    "text", ["a", "abc", "ab", " ", "\n", "-", "x3a", "a3", "\\1", "\\\\", "1a b"]
)
def test_a_unit_with_no_count_in_front_of_it_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize(
    "text", ["0a", "00a", "01a", "007a", "1a0b", "1a01b", "0\\1", "00\\\\", "10a05b"]
)
def test_a_zero_count_or_a_leading_zero_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize("text", ["3", "12", "1a2", "1a12", "3a4b5", "0", "99999999999"])
def test_a_count_with_no_unit_after_it_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize("text", ["\\", "3\\", "1a1\\", "12\\"])
def test_a_backslash_at_the_end_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize(
    "text", ["1\\a", "3\\ ", "1\\\n", "2\\x", "1a1\\b", "1\\\u0663", "1\\.", "2\\\u00e9"]
)
def test_a_backslash_before_anything_but_a_digit_or_backslash_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


def test_a_count_cannot_be_escaped_or_signed_or_start_with_zero():
    for text in ("\\31a", "+3a", "-3a", "0x3a", "3_0a"):
        with pytest.raises(ValueError):
            decode(text)


def test_an_error_late_in_the_text_still_raises():
    with pytest.raises(ValueError):
        decode("3a1b2c" * 100 + "d")
    with pytest.raises(ValueError):
        decode("3a1b2c" * 100 + "0d")
    with pytest.raises(ValueError):
        decode("3a1b2c" * 100 + "4")


def test_non_ascii_digits_are_not_counts():
    for text in ("\u0663a", "\uff13a", "3a\u0663", "\u00b2a"):
        with pytest.raises(ValueError):
            decode(text)
