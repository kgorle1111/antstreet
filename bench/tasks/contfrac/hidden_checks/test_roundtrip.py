import random
from fractions import Fraction

from contfrac import continued_fraction, convergents, from_continued_fraction


def test_rebuilding_the_expansion_gives_the_fraction_in_lowest_terms():
    rng = random.Random(14)
    for _ in range(1000):
        n, d = rng.randint(-10_000, 10_000), rng.choice([1, 2, 3, 7, 97, 1000, -5, -64, 12345])
        value = Fraction(n, d)
        assert from_continued_fraction(continued_fraction(n, d)) == (
            value.numerator,
            value.denominator,
        )


def test_the_last_convergent_is_the_value():
    rng = random.Random(15)
    for _ in range(500):
        n, d = rng.randint(-(10**9), 10**9), rng.randint(1, 10**9)
        value = Fraction(n, d)
        assert convergents(continued_fraction(n, d))[-1] == (value.numerator, value.denominator)


def test_expanding_the_rebuilt_value_gives_the_same_terms_when_the_last_term_is_not_one():
    rng = random.Random(16)
    for _ in range(500):
        terms = [rng.randint(-20, 20)] + [rng.randint(1, 30) for _ in range(rng.randint(0, 8))]
        if len(terms) > 1 and terms[-1] == 1:
            terms[-1] = 2
        p, q = from_continued_fraction(terms)
        assert continued_fraction(p, q) == terms


def test_a_last_term_of_one_expands_to_the_shorter_canonical_form():
    rng = random.Random(17)
    for _ in range(300):
        terms = [rng.randint(-9, 9)] + [rng.randint(1, 9) for _ in range(rng.randint(1, 6))]
        terms[-1] = 1
        p, q = from_continued_fraction(terms)
        canonical = continued_fraction(p, q)
        assert from_continued_fraction(canonical) == (p, q)
        assert canonical[-1] >= 2 or len(canonical) == 1


def test_the_expansion_of_a_fraction_with_a_huge_numerator_round_trips():
    n, d = 3**300 + 1, 2**250 - 7
    value = Fraction(n, d)
    assert from_continued_fraction(continued_fraction(n, d)) == (value.numerator, value.denominator)
