import random
from fractions import Fraction

from polyarith import (
    poly_add,
    poly_derivative,
    poly_divmod,
    poly_eval,
    poly_gcd,
    poly_mul,
)


def rand_poly(rng, max_len=6, fractions=True):
    out = []
    for _ in range(rng.randint(0, max_len)):
        if fractions and rng.random() < 0.4:
            out.append(Fraction(rng.randint(-6, 6), rng.randint(1, 5)))
        else:
            out.append(rng.randint(-6, 6))
    return out


def trimmed(p):
    p = list(p)
    while p and p[-1] == 0:
        p.pop()
    return p


def test_division_identity_and_degree_of_the_remainder():
    rng = random.Random(31)
    for _ in range(300):
        p, q = rand_poly(rng), rand_poly(rng, 4)
        if not trimmed(q):
            continue
        quotient, remainder = poly_divmod(p, q)
        assert poly_add(poly_mul(quotient, q), remainder) == trimmed(p)
        assert len(remainder) < len(trimmed(q))
        assert not quotient or quotient[-1] != 0
        assert not remainder or remainder[-1] != 0


def test_a_multiple_divides_exactly():
    rng = random.Random(2)
    for _ in range(100):
        q, r = rand_poly(rng, 4), rand_poly(rng, 4)
        if not trimmed(q):
            continue
        quotient, remainder = poly_divmod(poly_mul(q, r), q)
        assert remainder == []
        assert quotient == trimmed(r)


def test_evaluation_respects_sums_and_products():
    rng = random.Random(8)
    for _ in range(200):
        p, q = rand_poly(rng), rand_poly(rng)
        x = Fraction(rng.randint(-5, 5), rng.randint(1, 4))
        assert poly_eval(poly_add(p, q), x) == poly_eval(p, x) + poly_eval(q, x)
        assert poly_eval(poly_mul(p, q), x) == poly_eval(p, x) * poly_eval(q, x)


def test_the_product_rule():
    rng = random.Random(13)
    for _ in range(200):
        p, q = rand_poly(rng), rand_poly(rng)
        left = poly_derivative(poly_mul(p, q))
        right = poly_add(poly_mul(poly_derivative(p), q), poly_mul(p, poly_derivative(q)))
        assert left == right


def test_gcd_divides_both_is_monic_and_recovers_a_common_factor():
    rng = random.Random(77)
    for _ in range(150):
        common = rand_poly(rng, 3, fractions=False)
        p, q = rand_poly(rng, 3), rand_poly(rng, 3)
        if not trimmed(common) or not trimmed(p) or not trimmed(q):
            continue
        g = poly_gcd(poly_mul(p, common), poly_mul(q, common))
        assert g and g[-1] == 1
        assert poly_divmod(poly_mul(p, common), g)[1] == []
        assert poly_divmod(poly_mul(q, common), g)[1] == []
        assert poly_divmod(g, poly_gcd(common, common))[1] == []  # g is a multiple of monic(common)
        assert poly_gcd(p, q) == poly_gcd(q, p)


def test_large_coefficients_stay_exact():
    big = 10**40
    p = [big, 1]
    assert poly_eval(poly_mul(p, p), Fraction(1, big)) == (big + Fraction(1, big)) ** 2
    assert poly_eval(poly_mul(p, p), -big) == 0
    quotient, remainder = poly_divmod([big * big, 2 * big, 1], p)
    assert quotient == p and remainder == []
