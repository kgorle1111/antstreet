from fractions import Fraction

from contfrac import best_approximation

ROOT_TWO = Fraction(141421356237309504880168872420969807856967187537694, 10**50)


def test_a_huge_limit_returns_a_fraction_that_already_fits():
    assert best_approximation(6 * 10**40, 9 * 10**40, 10**40) == (2, 3)
    x = Fraction(12345678901234567890123, 10**30)
    assert best_approximation(12345678901234567890123, 10**30, 10**30) == (
        x.numerator,
        x.denominator,
    )
    assert best_approximation(12345678901234567890123, 10**30, 10**60) == (
        x.numerator,
        x.denominator,
    )


def test_a_huge_denominator_with_a_small_limit():
    n, d = 10**40 + 1, 10**40
    assert best_approximation(n, d, 10**20 - 5) == (1, 1)
    assert best_approximation(-n, d, 10**20 - 5) == (-1, 1)
    assert best_approximation(n, d, 1) == (1, 1)
    assert best_approximation(-n, d, 1) == (-1, 1)


def test_one_plus_a_tiny_number():
    x = (10**20 + 1, 10**20)
    # the neighbours of x with denominators below 10**20 are 1/1 and (10**20)/(10**20 - 1),
    # and the second one is far closer
    assert best_approximation(*x, 10**20 - 1) == (10**20, 10**20 - 1)
    assert best_approximation(*x, 10**20) == x
    assert best_approximation(*x, 3) == (1, 1)


def test_a_value_of_one_written_with_a_huge_numerator_and_denominator():
    assert best_approximation(10**30 + 1, 10**30 + 1, 5) == (1, 1)
    assert best_approximation(-(10**30), 10**30, 1) == (-1, 1)


def test_the_square_root_of_two_to_fifty_digits():
    n, d = ROOT_TWO.numerator, ROOT_TWO.denominator
    assert best_approximation(n, d, 1) == (1, 1)
    assert best_approximation(n, d, 2) == (3, 2)
    assert best_approximation(n, d, 5) == (7, 5)
    assert best_approximation(n, d, 70) == (99, 70)
    assert best_approximation(n, d, 100) == (140, 99)
    assert best_approximation(n, d, 985) == (1393, 985)
    # two neighbours of x with denominators b and d, b + d above the limit, are 1/(b*d) apart
    p, q = best_approximation(n, d, 10**30)
    assert 1 <= q <= 10**30
    assert abs(ROOT_TWO - Fraction(p, q)) <= Fraction(1, 2 * 10**30)
