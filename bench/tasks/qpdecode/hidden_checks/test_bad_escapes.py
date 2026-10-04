import pytest
from qpdecode import decode


@pytest.mark.parametrize(
    "text",
    [
        "=G1",
        "=1G",
        "=GG",
        "=1",
        "=1\r\nx",
        "=1\nx",
        "= ",
        "= 1",
        "=\t1",
        "==",
        "=3=",
    ],
)
def test_an_equals_sign_without_two_hex_digits_raises_value_error(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize("text", ["abc=G1def", "abc=1", "abc=Zz", "ok=41 and =4", "a=\r", "=\r"])
def test_the_bad_escape_is_found_anywhere_in_the_text(text):
    with pytest.raises(ValueError):
        decode(text)


@pytest.mark.parametrize(
    "text",
    ["=1\r\n3", "=1\n3", "a=\r\n=1\r\n", "=4\r\n1", "x=\t\ny", "a= \nb", "a=  \r\nb"],
)
def test_two_digits_may_not_be_split_by_a_line_break_or_followed_by_spaces_after_the_equals(text):
    with pytest.raises(ValueError):
        decode(text)


def test_the_equals_sign_before_a_carriage_return_that_is_not_part_of_a_line_break():
    with pytest.raises(ValueError):
        decode("a=\rb")
    with pytest.raises(ValueError):
        decode("a=\r")


def test_a_good_escape_after_a_bad_looking_one_is_still_checked_in_order():
    assert decode("=3D=41") == b"=A"
    with pytest.raises(ValueError):
        decode("=3D=4")


def test_escapes_that_are_valid_next_to_soft_breaks_do_not_raise():
    assert decode("=41=\r\n=42") == b"AB"
    assert decode("=41=") == b"A"
