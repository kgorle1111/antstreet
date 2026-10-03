from fractions import Fraction

import pytest
from polyarith import poly_divmod


@pytest.mark.parametrize(
    ("p", "q", "quotient", "remainder"),
    [
        ([-1, 0, 1], [1, 1], [-1, 1], []),
        ([1, 0, 0, 1], [1, 1], [1, -1, 1], []),
        ([5, 3], [1, 1], [3], [2]),
        ([1, 0, 1], [0, 1], [0, 1], [1]),
        ([1, 2], [1, 0, 1], [], [1, 2]),
        ([], [1, 2], [], []),
        ([1, 1], [1, 1], [1], []),
        ([1, 3, 2], [1, 2], [1, 1], []),
        ([1, 1, 1], [-2, 1], [3, 1], [7]),
        ([6], [4], [Fraction(3, 2)], []),
        ([0, 0, 0, 1], [0, 2], [0, 0, Fraction(1, 2)], []),
        ([0, 0, 1], [1, 2], [Fraction(-1, 4), Fraction(1, 2)], [Fraction(1, 4)]),
        ([1, 2, 3, 4, 5], [1, 0, 1], [-2, 4, 5], [3, -2]),
        ([1, 2, 3, 0, 0], [1, 0, 1, 0], [3], [-2, 2]),
    ],
)
def test_long_division(p, q, quotient, remainder):
    got_q, got_r = poly_divmod(p, q)
    assert got_q == quotient
    assert got_r == remainder


def test_the_remainder_drops_its_leading_zeros():
    # x^3 + x + 1 divided by x^2 + 1: x^3 + x cancels, so the remainder is the constant 1
    quotient, remainder = poly_divmod([1, 1, 0, 1], [1, 0, 1])
    assert quotient == [0, 1]
    assert remainder == [1]


def test_a_constant_divisor_scales():
    assert poly_divmod([2, 4, 6], [2]) == ([1, 2, 3], [])
    assert poly_divmod([1, 2, 3], [Fraction(1, 2)]) == ([2, 4, 6], [])


def test_the_result_is_a_pair_of_lists_of_fractions():
    got = poly_divmod([1, 1, 1], [-2, 1])
    assert isinstance(got, tuple) and len(got) == 2
    for part in got:
        assert isinstance(part, list)
        assert all(type(c) is Fraction for c in part)


@pytest.mark.parametrize("zero", [[], [0], [0, 0]])
def test_dividing_by_the_zero_polynomial_raises_zero_division_error(zero):
    with pytest.raises(ZeroDivisionError):
        poly_divmod([1, 2, 3], zero)
    with pytest.raises(ZeroDivisionError):
        poly_divmod([], zero)
