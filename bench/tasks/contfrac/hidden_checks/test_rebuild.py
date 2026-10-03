import pytest
from contfrac import from_continued_fraction


@pytest.mark.parametrize(
    ("terms", "value"),
    [
        ([4, 2, 6, 7], (415, 93)),
        ([-4, 2], (-7, 2)),
        ([1, 1], (2, 1)),
        ([0, 2], (1, 2)),
        ([5], (5, 1)),
        ([0], (0, 1)),
        ([-3], (-3, 1)),
        ([3, 7, 16], (355, 113)),
        ([3, 7], (22, 7)),
        ([1, 1, 1, 1, 2], (13, 8)),
        ([-5, 1, 1, 6, 7], (-415, 93)),
        ([-3, 1, 2], (-7, 3)),
        ([0, 1], (1, 1)),
        ([0, 1, 1], (1, 2)),
        ([2, 1, 1, 1], (8, 3)),
        ([142, 1, 6], (1000, 7)),
        ([1, 1, 1, 1, 1, 1, 1, 1, 1, 1], (89, 55)),
    ],
)
def test_values(terms, value):
    assert from_continued_fraction(terms) == value
    assert from_continued_fraction(tuple(terms)) == value


def test_a_last_term_of_one_is_accepted_and_equals_the_shorter_form():
    assert from_continued_fraction([4, 2, 6, 6, 1]) == from_continued_fraction([4, 2, 6, 7])
    assert from_continued_fraction([2, 1]) == (3, 1)
    assert from_continued_fraction([-1, 1]) == (0, 1)


def test_the_denominator_is_positive_and_the_fraction_is_in_lowest_terms():
    from math import gcd

    for terms in ([-7, 3, 5], [0, 4, 4, 4], [-1, 1, 1], [10, 2, 2, 2, 2], [-2, 6, 1, 9]):
        p, q = from_continued_fraction(terms)
        assert q > 0 and gcd(p, q) == 1


def test_big_terms_are_exact():
    big = 10**30
    assert from_continued_fraction([big, big]) == (big * big + 1, big)
    assert from_continued_fraction([0, big]) == (1, big)


def test_the_result_is_a_tuple_of_plain_ints():
    got = from_continued_fraction([4, 2, 6, 7])
    assert type(got) is tuple and len(got) == 2
    assert all(type(x) is int for x in got)
