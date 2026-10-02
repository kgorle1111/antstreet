import pytest
from moneysplit import split_by_ratio


@pytest.mark.parametrize(
    ("total", "ratios", "shares"),
    [
        (100, [1, 1, 1], [34, 33, 33]),
        (10, [1, 2], [3, 7]),
        (100, [1, 2, 3], [17, 33, 50]),
        (100, [3, 2, 1], [50, 33, 17]),
        (99, [50, 30, 20], [49, 30, 20]),
        (100, [50, 30, 20], [50, 30, 20]),
        (0, [1, 2], [0, 0]),
        (1000, [70, 20, 10], [700, 200, 100]),
        (1, [2, 1], [1, 0]),
        (1, [1, 2], [0, 1]),
    ],
)
def test_exact_values(total, ratios, shares):
    assert split_by_ratio(total, ratios) == shares


def test_the_cents_left_over_go_to_the_largest_fractional_part_not_to_the_first_share():
    # exact shares 16.67, 33.33, 50: the single left-over cent belongs to the first
    assert split_by_ratio(100, [1, 2, 3]) == [17, 33, 50]
    # exact shares 50, 33.33, 16.67: it belongs to the last
    assert split_by_ratio(100, [3, 2, 1]) == [50, 33, 17]
    # exact shares 3.33 and 6.67
    assert split_by_ratio(10, [1, 2]) == [3, 7]


def test_two_cents_left_over_go_to_the_two_largest_fractional_parts():
    # exact shares 49.5, 29.7, 19.8: floors add to 97, so the 0.8 and the 0.7 get a cent
    assert split_by_ratio(99, [50, 30, 20]) == [49, 30, 20]
    # exact shares 2.7, 3.6, 2.7 and 0: floors add to 7, the 2.7s tie, so both of them get one
    assert split_by_ratio(9, [3, 4, 3, 0]) == [3, 3, 3, 0]


def test_result_is_a_list_of_ints_with_one_share_per_ratio():
    shares = split_by_ratio(100, [1, 1, 1])
    assert isinstance(shares, list)
    assert len(shares) == 3
    assert all(type(s) is int for s in shares)


@pytest.mark.parametrize("make", [list, tuple, iter, lambda r: (x for x in r)])
def test_ratios_may_be_any_iterable(make):
    assert split_by_ratio(10, make([1, 2])) == [3, 7]
