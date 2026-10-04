from fractions import Fraction

import pytest
from polyarith import poly_add


@pytest.mark.parametrize(
    ("p", "q", "total"),
    [
        ([1, 2], [3, -2], [4]),
        ([1, 1], [-1, -1], []),
        ([1, 2, 3], [4, 5], [5, 7, 3]),
        ([], [1], [1]),
        ([1], [], [1]),
        ([], [], []),
        ([1, 2, 3], [0, 0, -3], [1, 2]),
        ([1, 0, 0], [2, 0], [3]),
        ([0, 0, 5], [0, 0, -5], []),
        ([1, 2, 3, 4], [-1, -2, -3, -4], []),
        ([10**30, 1], [10**30, 1], [2 * 10**30, 2]),
        ([-7], [7], []),
    ],
)
def test_sums(p, q, total):
    assert poly_add(p, q) == total
    assert poly_add(q, p) == total


def test_fraction_coefficients_stay_exact():
    assert poly_add([Fraction(1, 2)], [Fraction(1, 3)]) == [Fraction(5, 6)]
    assert poly_add([Fraction(1, 3), 1], [Fraction(2, 3), -1]) == [Fraction(1)]
    assert poly_add([Fraction(1, 10)], [Fraction(2, 10)]) == [Fraction(3, 10)]


def test_a_tuple_is_a_polynomial_too():
    assert poly_add((1, 2), (3, 4, 5)) == [4, 6, 5]
