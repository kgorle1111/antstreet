import pytest
from contfrac import best_approximation

PI = (314159265, 100000000)


@pytest.mark.parametrize(
    ("limit", "expected"),
    [
        (1, (3, 1)),
        (2, (3, 1)),
        (3, (3, 1)),
        (4, (13, 4)),
        (5, (16, 5)),
        (6, (19, 6)),
        (7, (22, 7)),
        (8, (22, 7)),
        (56, (22, 7)),
        (57, (179, 57)),
        (63, (179, 57)),
        (64, (201, 64)),
        (98, (289, 92)),
        (99, (311, 99)),
        (105, (311, 99)),
        (106, (333, 106)),
        (112, (333, 106)),
        (113, (355, 113)),
        (1000, (355, 113)),
    ],
)
def test_the_pi_table(limit, expected):
    assert best_approximation(*PI, limit) == expected


@pytest.mark.parametrize(
    ("n", "d", "limit", "expected"),
    [
        (3, 2, 1, (1, 1)),
        (-3, 2, 1, (-2, 1)),
        (1, 3, 2, (1, 2)),
        (1, 3, 1, (0, 1)),
        (2, 3, 1, (1, 1)),
        (5, 2, 1, (2, 1)),
        (-5, 2, 1, (-3, 1)),
        (7, 1, 5, (7, 1)),
        (0, 9, 3, (0, 1)),
        (6, 4, 2, (3, 2)),
        (6, 4, 1, (1, 1)),
        (-6, -4, 2, (3, 2)),
        (6, -4, 2, (-3, 2)),
        (1, 7, 3, (0, 1)),
        (1, 7, 4, (1, 4)),
        (1, 7, 7, (1, 7)),
        (1, 7, 100, (1, 7)),
        (415, 93, 13, (58, 13)),
        (415, 93, 12, (49, 11)),
        (415, 93, 93, (415, 93)),
    ],
)
def test_small_cases_and_ties(n, d, limit, expected):
    assert best_approximation(n, d, limit) == expected


def test_a_number_that_fits_is_returned_in_lowest_terms():
    assert best_approximation(10, 4, 2) == (5, 2)
    assert best_approximation(100, 20, 1) == (5, 1)
    assert best_approximation(-9, 6, 2) == (-3, 2)


def test_the_result_is_a_tuple_of_plain_ints_with_a_positive_denominator():
    got = best_approximation(*PI, 50)
    assert type(got) is tuple and len(got) == 2
    assert all(type(x) is int for x in got) and got[1] > 0
