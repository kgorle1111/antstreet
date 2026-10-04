import pytest
from contfrac import continued_fraction


@pytest.mark.parametrize(
    ("n", "d", "terms"),
    [
        (415, 93, [4, 2, 6, 7]),
        (-7, 2, [-4, 2]),
        (7, -3, [-3, 1, 2]),
        (1, 2, [0, 2]),
        (3, 1, [3]),
        (0, 5, [0]),
        (6, 4, [1, 2]),
        (7, 3, [2, 3]),
        (-3, 1, [-3]),
        (-1, 2, [-1, 2]),
        (-1, 3, [-1, 1, 2]),
        (1, 3, [0, 3]),
        (13, 8, [1, 1, 1, 1, 2]),
        (355, 113, [3, 7, 16]),
        (22, 7, [3, 7]),
        (-415, -93, [4, 2, 6, 7]),
        (-415, 93, [-5, 1, 1, 6, 7]),
        (0, -5, [0]),
        (10, 5, [2]),
        (1, 1, [1]),
        (-5, -1, [5]),
        (1000, 7, [142, 1, 6]),
    ],
)
def test_expansions(n, d, terms):
    assert continued_fraction(n, d) == terms


def test_the_last_term_is_at_least_two_when_there_are_several():
    for n in range(-30, 31):
        for d in (1, 2, 3, 5, 7, 8, 12, -3, -8):
            terms = continued_fraction(n, d)
            assert terms[1:] == [t for t in terms[1:] if t >= 1]
            if len(terms) > 1:
                assert terms[-1] >= 2, (n, d, terms)


def test_the_first_term_is_the_floor():
    for n in range(-40, 41):
        for d in (1, 2, 3, 7, 10, -2, -7):
            assert continued_fraction(n, d)[0] == n // d


def test_a_fraction_not_in_lowest_terms_gives_the_same_terms():
    assert continued_fraction(830, 186) == continued_fraction(415, 93)
    assert continued_fraction(-14, 4) == continued_fraction(-7, 2)
    assert continued_fraction(0, 17) == [0]


def test_the_result_is_a_list_of_plain_ints():
    got = continued_fraction(415, 93)
    assert isinstance(got, list) and all(type(t) is int for t in got)


def test_large_numbers_are_exact():
    n, d = 10**40 + 7, 10**20 + 3
    terms = continued_fraction(n, d)
    assert terms[0] == n // d
    assert all(t >= 1 for t in terms[1:])
    assert continued_fraction(2**200, 3**100)[0] == 2**200 // 3**100
