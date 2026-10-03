from fractions import Fraction

import pytest
from polyarith import (
    poly_add,
    poly_derivative,
    poly_divmod,
    poly_eval,
    poly_gcd,
    poly_mul,
    poly_str,
)

TWO = [poly_add, poly_mul, poly_divmod, poly_gcd]
ONE = [poly_derivative, poly_str]


@pytest.mark.parametrize("bad", [None, 5, "123", {1: 2}, {1, 2}, Fraction(1, 2), 1.5])
def test_a_polynomial_that_is_not_a_list_raises_type_error(bad):
    for fn in TWO:
        with pytest.raises(TypeError):
            fn(bad, [1, 2])
        with pytest.raises(TypeError):
            fn([1, 2], bad)
    for fn in ONE:
        with pytest.raises(TypeError):
            fn(bad)
    with pytest.raises(TypeError):
        poly_eval(bad, 1)


@pytest.mark.parametrize("bad", [1.0, 0.5, "1", None, True, False, 1 + 2j, [1], b"1"])
def test_a_coefficient_that_is_not_an_int_or_fraction_raises_type_error(bad):
    for fn in TWO:
        with pytest.raises(TypeError):
            fn([1, bad], [1, 2])
        with pytest.raises(TypeError):
            fn([1, 2], [bad, 1])
    for fn in ONE:
        with pytest.raises(TypeError):
            fn([1, bad, 2])
    with pytest.raises(TypeError):
        poly_eval([1, bad], 1)


@pytest.mark.parametrize("bad", [1.0, 0.5, "1", None, True, 1 + 2j])
def test_x_must_be_an_int_or_fraction(bad):
    with pytest.raises(TypeError):
        poly_eval([1, 2], bad)
    with pytest.raises(TypeError):
        poly_eval([], bad)


def test_a_bad_coefficient_is_found_even_when_it_would_not_matter():
    with pytest.raises(TypeError):
        poly_mul([], [1.5])
    with pytest.raises(TypeError):
        poly_divmod([1.5], [1, 1])
    with pytest.raises(TypeError):
        poly_gcd([1, 1], [0.5])
    with pytest.raises(TypeError):
        poly_add([0, 0.0], [1])


def test_division_by_zero_is_zero_division_error_not_value_error():
    with pytest.raises(ZeroDivisionError):
        poly_divmod([1], [])
