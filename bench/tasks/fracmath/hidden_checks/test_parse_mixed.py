import pytest
from fracmath import parse_fraction


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1 1/2", (3, 2)),
        ("2 3/4", (11, 4)),
        ("10 1/3", (31, 3)),
        ("0 3/4", (3, 4)),
        ("1 0/5", (1, 1)),
        ("5 0/1", (5, 1)),
        ("3 1/1000", (3001, 1000)),
        ("12 11/12", (155, 12)),
    ],
)
def test_mixed_numbers(text, value):
    assert parse_fraction(text) == value


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("-1 1/2", (-3, 2)),
        ("-2 3/4", (-11, 4)),
        ("-10 1/3", (-31, 3)),
        ("-1 0/5", (-1, 1)),
        ("-12 11/12", (-155, 12)),
    ],
)
def test_a_minus_sign_negates_the_whole_mixed_number(text, value):
    # -1 1/2 is -(1 + 1/2), not -1 + 1/2
    assert parse_fraction(text) == value


@pytest.mark.parametrize("text", ["-0 1/2", "-0 3/6"])
def test_minus_zero_and_a_fraction_is_negative(text):
    assert parse_fraction(text) == (-1, 2)


def test_minus_zero_with_a_zero_fraction_is_zero():
    assert parse_fraction("-0 0/5") == (0, 1)
    assert parse_fraction("0 0/5") == (0, 1)


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("1 2/4", (3, 2)),
        ("2 2/6", (7, 3)),
        ("1 6/10", (8, 5)),
        ("-1 2/4", (-3, 2)),
        ("0 2/4", (1, 2)),
    ],
)
def test_the_fraction_part_is_reduced_too(text, value):
    assert parse_fraction(text) == value


@pytest.mark.parametrize("text", ["1  1/2", "1   1/2", "1\t1/2", "1 \t 1/2", "1 \t\t 1/2"])
def test_any_spaces_or_tabs_between_the_whole_part_and_the_fraction(text):
    assert parse_fraction(text) == (3, 2)


@pytest.mark.parametrize("text", ["  1 1/2", "1 1/2  ", "\t1 1/2\n", "  -1 1/2  "])
def test_whitespace_around_a_mixed_number(text):
    assert parse_fraction(text) in {(3, 2), (-3, 2)}


@pytest.mark.parametrize("text", ["01 01/02", "001 1/002"])
def test_leading_zeros_in_a_mixed_number(text):
    assert parse_fraction(text) == (3, 2)


@pytest.mark.parametrize(
    "text", ["1 2/2", "1 3/2", "1 5/3", "1 4/4", "0 1/1", "0 5/3", "-1 7/7", "2 10/5", "1 1/1"]
)
def test_the_fraction_in_a_mixed_number_must_be_proper(text):
    with pytest.raises(ValueError):
        parse_fraction(text)
