import pytest
from moneysplit import split_even


@pytest.mark.parametrize(
    ("total", "parts", "shares"),
    [
        (10, 3, [4, 3, 3]),
        (9, 3, [3, 3, 3]),
        (1, 3, [1, 0, 0]),
        (0, 4, [0, 0, 0, 0]),
        (100, 1, [100]),
        (5, 2, [3, 2]),
        (7, 4, [2, 2, 2, 1]),
        (100, 7, [15, 15, 14, 14, 14, 14, 14]),
        (2, 5, [1, 1, 0, 0, 0]),
        (1000, 3, [334, 333, 333]),
    ],
)
def test_the_first_shares_get_the_extra_cents(total, parts, shares):
    assert split_even(total, parts) == shares


def test_one_share_per_part_and_nothing_lost():
    for total in range(0, 200):
        for parts in range(1, 13):
            shares = split_even(total, parts)
            assert len(shares) == parts
            assert sum(shares) == total
            assert max(shares) - min(shares) <= 1
            assert shares == sorted(shares, reverse=True)


def test_shares_are_ints_in_a_list():
    shares = split_even(10, 3)
    assert isinstance(shares, list)
    assert all(type(s) is int for s in shares)
