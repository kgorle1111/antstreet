from fractions import Fraction

from polyarith import poly_add, poly_derivative, poly_divmod, poly_gcd, poly_mul


def all_fractions(p):
    return isinstance(p, list) and all(type(c) is Fraction for c in p)


def test_results_are_lists_of_fractions():
    assert all_fractions(poly_add([1, 2], [3, 4]))
    assert all_fractions(poly_mul([1, 2], [3, 4]))
    assert all_fractions(poly_derivative([1, 2, 3]))
    assert all_fractions(poly_gcd([-1, 0, 1], [1, 1]))
    quotient, remainder = poly_divmod([1, 0, 1], [1, 1])
    assert all_fractions(quotient) and all_fractions(remainder)


def test_no_trailing_zeros_in_any_result():
    assert poly_add([1, 2, 3], [0, 0, -3]) == [1, 2]
    assert poly_mul([2, 0, 0], [3, 0]) == [6]
    assert poly_derivative([1, 2, 0]) == [2]
    assert poly_divmod([1, 1, 1], [1, 1, 1]) == ([1], [])
    assert poly_divmod([0, 0, 0], [1]) == ([], [])


def test_the_zero_polynomial_is_the_empty_list_everywhere():
    assert poly_add([0], [0, 0]) == []
    assert poly_mul([0, 0], [5]) == []
    assert poly_derivative([0]) == []
    assert poly_divmod([0, 0], [3]) == ([], [])
    assert poly_gcd([0], [0, 0]) == []


def test_inputs_are_not_changed_and_results_are_new_lists():
    p, q = [1, 2, 3, 4], [1, 1]
    p_before, q_before = list(p), list(q)
    poly_add(p, q)
    poly_mul(p, q)
    poly_divmod(p, q)
    poly_gcd(p, q)
    poly_derivative(p)
    assert p == p_before and q == q_before
    same = poly_add(p, [])
    assert same == p and same is not p
    same = poly_mul(p, [1])
    assert same is not p


def test_tuples_work_everywhere_and_give_lists():
    assert poly_add((1,), (2,)) == [3]
    assert poly_mul((1, 1), (1, 1)) == [1, 2, 1]
    assert poly_divmod((-1, 0, 1), (1, 1)) == ([-1, 1], [])
    assert poly_gcd((-1, 0, 1), (1, 1)) == [1, 1]
    assert poly_derivative((1, 1)) == [1]
