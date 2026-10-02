import pytest
from fracmath import parse_fraction


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("3/4", (3, 4)),
        ("1/2", (1, 2)),
        ("7/3", (7, 3)),
        ("5", (5, 1)),
        ("0", (0, 1)),
        ("42", (42, 1)),
        ("-5", (-5, 1)),
        ("-3/4", (-3, 4)),
        ("-1/2", (-1, 2)),
        ("-7/3", (-7, 3)),
        ("100/1", (100, 1)),
    ],
)
def test_whole_numbers_and_fractions(text, value):
    assert parse_fraction(text) == value


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("6/4", (3, 2)),
        ("4/2", (2, 1)),
        ("10/5", (2, 1)),
        ("2/4", (1, 2)),
        ("12/18", (2, 3)),
        ("100/400", (1, 4)),
        ("-6/4", (-3, 2)),
        ("-4/2", (-2, 1)),
        ("9/3", (3, 1)),
        ("7/7", (1, 1)),
        ("21/14", (3, 2)),
    ],
)
def test_the_result_is_in_lowest_terms(text, value):
    assert parse_fraction(text) == value


@pytest.mark.parametrize("text", ["0/5", "0/1", "0/100", "-0/5", "-0", "00", "0/007"])
def test_zero_is_zero_over_one(text):
    assert parse_fraction(text) == (0, 1)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("007", (7, 1)),
        ("03/04", (3, 4)),
        ("0003/0004", (3, 4)),
        ("-007/003", (-7, 3)),
        ("010", (10, 1)),
    ],
)
def test_leading_zeros_are_fine(text, value):
    assert parse_fraction(text) == value


@pytest.mark.parametrize(
    "text", ["  3/4", "3/4  ", "\t3/4\n", "  3/4  ", " 5 ", "\n-3/4\n", "  1 1/2  "]
)
def test_whitespace_around_the_whole_text(text):
    assert parse_fraction(text) in {(3, 4), (5, 1), (-3, 4), (3, 2)}


def test_a_negative_fraction_keeps_the_sign_on_the_numerator():
    num, den = parse_fraction("-3/4")
    assert (num, den) == (-3, 4)
    assert den > 0


def test_the_result_is_a_tuple_of_ints():
    for text in ("3/4", "5", "-1 1/2", "0"):
        result = parse_fraction(text)
        assert type(result) is tuple
        assert len(result) == 2
        assert all(type(part) is int for part in result)


def test_big_numbers_are_exact():
    assert parse_fraction("123456789012345678901234567890/10") == (12345678901234567890123456789, 1)
    assert parse_fraction("1/100000000000000000000000") == (1, 10**23)
    assert parse_fraction("-99999999999999999999/3") == (-33333333333333333333, 1)
