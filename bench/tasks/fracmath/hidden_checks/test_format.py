import pytest
from fracmath import format_fraction


@pytest.mark.parametrize(
    ("num", "den", "text"),
    [
        (3, 4, "3/4"),
        (1, 2, "1/2"),
        (-3, 4, "-3/4"),
        (5, 1, "5"),
        (-2, 1, "-2"),
        (0, 1, "0"),
        (7, 1, "7"),
        (99, 100, "99/100"),
    ],
)
def test_whole_numbers_and_proper_fractions(num, den, text):
    assert format_fraction(num, den) == text


@pytest.mark.parametrize(
    ("num", "den", "text"),
    [
        (3, 2, "1 1/2"),
        (7, 2, "3 1/2"),
        (-7, 2, "-3 1/2"),
        (-3, 2, "-1 1/2"),
        (11, 4, "2 3/4"),
        (31, 3, "10 1/3"),
        (-31, 3, "-10 1/3"),
        (1001, 1000, "1 1/1000"),
        (155, 12, "12 11/12"),
    ],
)
def test_improper_fractions_become_mixed_numbers(num, den, text):
    assert format_fraction(num, den) == text


@pytest.mark.parametrize(
    ("num", "den", "text"),
    [
        (6, 4, "1 1/2"),
        (4, 2, "2"),
        (10, 5, "2"),
        (2, 4, "1/2"),
        (12, 18, "2/3"),
        (-6, 4, "-1 1/2"),
        (-4, 2, "-2"),
        (100, 400, "1/4"),
        (9, 3, "3"),
        (7, 7, "1"),
        (-7, 7, "-1"),
        (14, 4, "3 1/2"),
        (50, 100, "1/2"),
    ],
)
def test_the_value_is_reduced_first(num, den, text):
    assert format_fraction(num, den) == text


@pytest.mark.parametrize(
    ("num", "den", "text"),
    [
        (1, -2, "-1/2"),
        (-1, -2, "1/2"),
        (3, -4, "-3/4"),
        (-3, -4, "3/4"),
        (7, -2, "-3 1/2"),
        (-7, -2, "3 1/2"),
        (4, -2, "-2"),
        (-4, -2, "2"),
        (5, -1, "-5"),
        (6, -4, "-1 1/2"),
    ],
)
def test_a_negative_denominator_moves_the_sign_to_the_value(num, den, text):
    assert format_fraction(num, den) == text


@pytest.mark.parametrize("den", [1, 2, 5, -1, -2, -5, 100, -100])
def test_zero_has_no_sign_and_is_just_0(den):
    assert format_fraction(0, den) == "0"


def test_huge_values_are_exact():
    assert format_fraction(10**30 + 1, 10**30) == "1 1/1000000000000000000000000000000"
    assert format_fraction(-(10**30), 3) == "-333333333333333333333333333333 1/3"
    assert format_fraction(2 * 10**25, 4 * 10**25) == "1/2"


def test_the_result_is_a_str():
    assert isinstance(format_fraction(3, 2), str)
    assert isinstance(format_fraction(0, 1), str)


@pytest.mark.parametrize(
    ("num", "den"),
    [(1, 0), (0, 0), (-1, 0), (5, 0), (10**30, 0)],
)
def test_a_zero_denominator_is_a_value_error(num, den):
    with pytest.raises(ValueError):
        format_fraction(num, den)


@pytest.mark.parametrize(
    ("num", "den"),
    [
        (1.5, 2),
        (1, 2.0),
        ("1", 2),
        (1, "2"),
        (None, 2),
        (1, None),
        (True, 2),
        (1, True),
        (False, 1),
        ([1], 2),
    ],
)
def test_arguments_that_are_not_ints_are_type_errors(num, den):
    with pytest.raises(TypeError):
        format_fraction(num, den)
