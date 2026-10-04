import random
from fractions import Fraction

from contfrac import best_approximation


def brute_force(n, d, limit):
    """Try every denominator and both neighbours of x * q, then pick by (error, q, p)."""
    x = Fraction(n, d)
    best = None
    for q in range(1, limit + 1):
        floor = (x * q).__floor__()
        for p in (floor, floor + 1):
            key = (abs(x - Fraction(p, q)), q, p)
            if best is None or key < best:
                best = key
    return best[2], best[1]


def test_random_fractions_against_trying_every_denominator():
    rng = random.Random(77)
    for _ in range(1500):
        d = rng.choice([1, 2, 3, 5, 6, 7, 12, 30, 97, 360, 1001])
        n = rng.randint(-3000, 3000)
        if rng.random() < 0.3:
            n, d = -n, -d
        limit = rng.randint(1, 60)
        assert best_approximation(n, d, limit) == brute_force(n, d, limit), (n, d, limit)


def test_every_limit_for_a_few_fractions():
    for n, d in ((314159265, 100000000), (-17, 12), (1, 3), (22, 7), (7, 22), (-1, 1000)):
        for limit in range(1, 120):
            assert best_approximation(n, d, limit) == brute_force(n, d, limit), (n, d, limit)


def test_many_ties_from_halves_and_thirds():
    for n in range(-24, 25):
        for d in (2, 4, 6):
            for limit in (1, 2, 3):
                assert best_approximation(n, d, limit) == brute_force(n, d, limit), (n, d, limit)


def test_a_number_between_two_integers_exactly_halfway_picks_the_smaller():
    for k in range(-5, 6):
        assert best_approximation(2 * k + 1, 2, 1) == (k, 1)


def test_a_limit_above_the_denominator_returns_the_fraction_itself():
    rng = random.Random(1)
    for _ in range(300):
        d = rng.randint(1, 200)
        n = rng.randint(-1000, 1000)
        value = Fraction(n, d)
        assert best_approximation(n, d, d + rng.randint(0, 50)) == (
            value.numerator,
            value.denominator,
        )
