from fractions import Fraction

import pytest
from polyarith import poly_derivative, poly_gcd


@pytest.mark.parametrize(
    ("p", "d"),
    [
        ([5, 4, 3], [4, 6]),
        ([7], []),
        ([], []),
        ([0, 0, 0, 1], [0, 0, 3]),
        ([1, 2, 3, 4], [2, 6, 12]),
        ([1, 2, 0, 0], [2]),
        ([0, Fraction(1, 2), Fraction(1, 3)], [Fraction(1, 2), Fraction(2, 3)]),
        ([3, 0, 0, 0, 5], [0, 0, 0, 20]),
    ],
)
def test_derivative(p, d):
    assert poly_derivative(p) == d


@pytest.mark.parametrize(
    ("p", "q", "g"),
    [
        ([-1, 0, 1], [1, 2, 1], [1, 1]),
        ([1, 1], [2, 1], [1]),
        ([], [2, 4], [Fraction(1, 2), 1]),
        ([2, 4], [], [Fraction(1, 2), 1]),
        ([], [], []),
        ([3], [5], [1]),
        ([], [5], [1]),
        ([2, -3, 1], [-5, 4, 1], [-1, 1]),
        ([6, -9, 3], [-5, 4, 1], [-1, 1]),
        ([2, 4, 2], [2, 4, 2], [1, 2, 1]),
        ([-3, -5, -1, 1], [9, 3, -5, 1], [-3, -2, 1]),
        ([Fraction(1, 2), Fraction(1, 2)], [1, 1], [1, 1]),
        ([0, 0, 2], [0, 3], [0, 1]),
        ([1, 2, 1, 0], [1, 1], [1, 1]),
    ],
)
def test_gcd_is_monic(p, q, g):
    assert poly_gcd(p, q) == g
    assert poly_gcd(q, p) == g


def test_gcd_leading_coefficient_is_one_whatever_the_scale():
    g = poly_gcd([10, 20, 10], [30, 30])
    assert g == [1, 1]
    assert all(type(c) is Fraction for c in g)
    assert poly_gcd([Fraction(3), Fraction(3)], [7, 7]) == [1, 1]
