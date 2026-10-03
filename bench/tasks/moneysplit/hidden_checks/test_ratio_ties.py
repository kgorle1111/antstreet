import pytest
from moneysplit import split_by_ratio


@pytest.mark.parametrize(
    ("total", "ratios", "shares"),
    [
        (1, [1, 1], [1, 0]),
        (1, [1, 1, 1], [1, 0, 0]),
        (2, [1, 1, 1], [1, 1, 0]),
        (5, [1, 1, 1, 1], [2, 1, 1, 1]),
        (7, [1, 1, 1, 1], [2, 2, 2, 1]),
        (1, [1, 2, 1], [0, 1, 0]),
        (3, [1, 2, 1, 2], [1, 1, 0, 1]),
        (1, [5, 5], [1, 0]),
        (100, [1, 1, 1], [34, 33, 33]),
    ],
)
def test_equal_fractional_parts_go_to_the_earlier_share(total, ratios, shares):
    assert split_by_ratio(total, ratios) == shares


def test_a_larger_fractional_part_beats_an_earlier_position():
    # exact shares 0.2, 0.3, 0.5 and none of them rounds up on its own: the cent goes to the 0.5
    assert split_by_ratio(1, [2, 3, 5]) == [0, 0, 1]
    # exact shares 1.4, 1.6: the left-over cent goes to the second
    assert split_by_ratio(3, [7, 8]) == [1, 2]
    # exact shares 2.4, 2.6 -> floors 2 and 2, left over 1 -> second
    assert split_by_ratio(5, [12, 13]) == [2, 3]


def test_a_tie_is_broken_by_position_even_when_a_later_share_is_larger():
    # exact shares 2.5, 2.5, 5.0: the left-over cent has to go to the first of the two tied
    assert split_by_ratio(10, [1, 1, 2]) == [3, 2, 5]
    # exact shares 0.5, 0.5 and 1.0 in another order
    assert split_by_ratio(2, [1, 2, 1]) == [1, 1, 0]
