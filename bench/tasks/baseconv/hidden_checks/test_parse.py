from fractions import Fraction

import pytest
from baseconv import parse_number


@pytest.mark.parametrize(
    ("text", "base", "value"),
    [
        ("ff.8", 16, Fraction(511, 2)),
        ("-0.1", 2, Fraction(-1, 2)),
        ("007", 10, Fraction(7)),
        ("Z", 36, Fraction(35)),
        ("-0", 10, Fraction(0)),
        ("0", 2, Fraction(0)),
        ("0.1", 10, Fraction(1, 10)),
        ("1.1", 2, Fraction(3, 2)),
        ("A.A", 16, Fraction(85, 8)),
        ("a.a", 16, Fraction(85, 8)),
        ("-12.5", 10, Fraction(-25, 2)),
        ("10", 36, Fraction(36)),
        ("0.01", 2, Fraction(1, 4)),
        ("0.00", 10, Fraction(0)),
        ("-0.000", 10, Fraction(0)),
        ("12", 3, Fraction(5)),
        ("1.2", 3, Fraction(5, 3)),
        ("zz.zz", 36, Fraction(35 * 36 + 35) + Fraction(35 * 36 + 35, 36**2)),
    ],
)
def test_exact_values(text, base, value):
    got = parse_number(text, base)
    assert got == value
    assert type(got) is Fraction


def test_a_long_fraction_is_exact():
    text = "0." + "1" * 40
    assert parse_number(text, 10) == Fraction(int("1" * 40), 10**40)
    assert parse_number("0." + "3" * 30, 4) == Fraction(int("3" * 30, 4), 4**30)
    assert parse_number("1" + "0" * 70, 2) == 2**70


def test_a_number_with_many_digits_after_the_point_has_a_power_of_the_base_as_denominator():
    got = parse_number("0.0000000001", 2)
    assert got == Fraction(1, 2**10)
    assert parse_number("0.01", 10) == Fraction(1, 100)
