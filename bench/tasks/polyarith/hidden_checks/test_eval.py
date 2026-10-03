from fractions import Fraction

import pytest
from polyarith import poly_eval


@pytest.mark.parametrize(
    ("p", "x", "value"),
    [
        ([1, 2, 3], 2, 17),
        ([1, 2, 3], 0, 1),
        ([1, 2, 3], -1, 2),
        ([1, 2, 3], Fraction(1, 2), Fraction(11, 4)),
        ([], 5, 0),
        ([0, 0], Fraction(3, 7), 0),
        ([7], 100, 7),
        ([0, 0, 0, 1], 10**20, 10**60),
        ([-1, 0, 1], 1, 0),
        ([Fraction(1, 3), Fraction(1, 6)], 2, Fraction(2, 3)),
        ([1, 2, 3, 0, 0], 2, 17),
        ([1, 1, 1, 1], Fraction(-1, 2), Fraction(5, 8)),
    ],
)
def test_values(p, x, value):
    assert poly_eval(p, x) == value


def test_the_result_is_a_fraction_and_exact():
    got = poly_eval([1, 2, 3], 2)
    assert type(got) is Fraction
    assert type(poly_eval([], 1)) is Fraction
    third = Fraction(1, 3)
    assert poly_eval([1, 3, 3, 1], third) == Fraction(64, 27)
    assert poly_eval([0, 3], third) == 1


def test_a_root_gives_exactly_zero():
    # (x - 1/3)(x + 2) = x^2 + (5/3)x - 2/3
    p = [Fraction(-2, 3), Fraction(5, 3), 1]
    assert poly_eval(p, Fraction(1, 3)) == 0
    assert poly_eval(p, -2) == 0
