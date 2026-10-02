import pytest
from moneysplit import split_by_ratio, split_even


@pytest.mark.parametrize(
    ("total", "ratios", "shares"),
    [
        (-100, [1, 1, 1], [-34, -33, -33]),
        (-10, [1, 2], [-3, -7]),
        (-7, [1, 1], [-4, -3]),
        (-1, [1, 1], [-1, 0]),
        (-100, [1, 2, 3], [-17, -33, -50]),
        (-1, [0, 1], [0, -1]),
    ],
)
def test_negative_total_by_ratio(total, ratios, shares):
    assert split_by_ratio(total, ratios) == shares


@pytest.mark.parametrize(
    ("total", "parts", "shares"),
    [(-10, 3, [-4, -3, -3]), (-1, 3, [-1, 0, 0]), (-9, 3, [-3, -3, -3]), (-5, 1, [-5])],
)
def test_negative_total_split_evenly(total, parts, shares):
    assert split_even(total, parts) == shares


def test_a_negative_total_is_the_negation_of_the_positive_split():
    for total in range(1, 80):
        for ratios in ([1, 1, 1], [1, 2], [5, 3, 2], [0, 1, 6], [2, 2, 3, 3]):
            assert split_by_ratio(-total, ratios) == [-s for s in split_by_ratio(total, ratios)]


def test_zero_gives_all_zeros_and_no_negative_zero_surprises():
    assert split_by_ratio(0, [1, 2, 3]) == [0, 0, 0]
    assert split_even(0, 3) == [0, 0, 0]
    assert all(type(s) is int for s in split_even(0, 3))
