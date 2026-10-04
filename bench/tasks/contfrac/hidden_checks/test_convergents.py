from math import gcd

import pytest
from contfrac import continued_fraction, convergents, from_continued_fraction


@pytest.mark.parametrize(
    ("terms", "expected"),
    [
        ([4, 2, 6, 7], [(4, 1), (9, 2), (58, 13), (415, 93)]),
        ([-4, 2], [(-4, 1), (-7, 2)]),
        ([3, 7, 16], [(3, 1), (22, 7), (355, 113)]),
        ([5], [(5, 1)]),
        ([0, 2], [(0, 1), (1, 2)]),
        ([1, 1, 1, 1, 2], [(1, 1), (2, 1), (3, 2), (5, 3), (13, 8)]),
        ([-3, 1, 2], [(-3, 1), (-2, 1), (-7, 3)]),
        ([0], [(0, 1)]),
        ([1, 2, 2, 2, 2], [(1, 1), (3, 2), (7, 5), (17, 12), (41, 29)]),
        ([2, 1, 1], [(2, 1), (3, 1), (5, 2)]),
    ],
)
def test_known_convergents(terms, expected):
    assert convergents(terms) == expected
    assert convergents(tuple(terms)) == expected


def test_each_convergent_is_the_value_of_that_many_leading_terms():
    for terms in ([4, 2, 6, 7], [-5, 1, 1, 6, 7], [0, 3, 1, 4, 1, 5], [1, 1, 1, 1, 1, 1, 1]):
        got = convergents(terms)
        assert len(got) == len(terms)
        for k in range(1, len(terms) + 1):
            assert got[k - 1] == from_continued_fraction(terms[:k])


def test_every_convergent_is_in_lowest_terms_with_a_positive_denominator():
    for terms in ([4, 2, 6, 7], [-5, 1, 1, 6, 7], [0, 3, 1, 4, 1, 5], [7, 1, 1, 1, 1]):
        for p, q in convergents(terms):
            assert q > 0 and gcd(p, q) == 1


def test_neighbouring_convergents_differ_by_one_over_the_product_of_denominators():
    terms = continued_fraction(1000003, 7919)
    got = convergents(terms)
    for k in range(1, len(got)):
        (p0, q0), (p1, q1) = got[k - 1], got[k]
        assert p1 * q0 - p0 * q1 == (-1) ** (k + 1)


def test_the_last_convergent_is_the_whole_number_and_denominators_grow():
    n, d = 1000003, 7919
    got = convergents(continued_fraction(n, d))
    assert got[-1] == (n // gcd(n, d), d // gcd(n, d))
    dens = [q for _, q in got]
    assert dens == sorted(dens)


def test_a_last_term_of_one_and_big_terms():
    assert convergents([2, 1]) == [(2, 1), (3, 1)]
    big = 10**25
    assert convergents([0, big, big]) == [(0, 1), (1, big), (big, big * big + 1)]


def test_the_result_is_a_list_of_tuples_of_plain_ints():
    got = convergents([4, 2, 6, 7])
    assert isinstance(got, list)
    assert all(type(pair) is tuple and all(type(x) is int for x in pair) for pair in got)
