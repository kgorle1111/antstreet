from fractions import Fraction

import pytest
from polyarith import poly_mul


@pytest.mark.parametrize(
    ("p", "q", "product"),
    [
        ([1, 1], [1, 1], [1, 2, 1]),
        ([1, 2, 3], [4, 5], [4, 13, 22, 15]),
        ([-1, 1], [1, 1], [-1, 0, 1]),
        ([2], [3], [6]),
        ([0, 1], [0, 1], [0, 0, 1]),
        ([1, 2, 3], [1], [1, 2, 3]),
        ([1, 2, 3], [0, 1], [0, 1, 2, 3]),
        ([1, 2, 3, 0, 0], [2, 0], [2, 4, 6]),
        ([1, -1], [1, 1, 1], [1, 0, 0, -1]),
        ([10**30, 1], [10**30, 1], [10**60, 2 * 10**30, 1]),
    ],
)
def test_products(p, q, product):
    assert poly_mul(p, q) == product
    assert poly_mul(q, p) == product


@pytest.mark.parametrize("zero", [[], [0], [0, 0, 0]])
def test_anything_times_zero_is_the_zero_polynomial(zero):
    assert poly_mul(zero, [1, 2, 3]) == []
    assert poly_mul([1, 2, 3], zero) == []
    assert poly_mul(zero, zero) == []


def test_fraction_coefficients_stay_exact():
    assert poly_mul([Fraction(1, 2), 1], [2]) == [1, 2]
    assert poly_mul([Fraction(1, 2), Fraction(1, 3)], [Fraction(2), Fraction(3)]) == [
        Fraction(1),
        Fraction(3, 2) + Fraction(2, 3),
        Fraction(1),
    ]
    assert poly_mul([Fraction(1, 3)], [3]) == [Fraction(1)]


def test_the_product_of_three_binomials():
    step = poly_mul(poly_mul([-1, 1], [-2, 1]), [-3, 1])
    assert step == [-6, 11, -6, 1]
