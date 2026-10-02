import itertools

from moneysplit import split_by_ratio

RATIOS = [
    [1],
    [1, 1],
    [1, 2],
    [2, 1],
    [1, 1, 1],
    [1, 2, 3],
    [3, 1, 2],
    [5, 3, 2],
    [1, 1, 1, 1],
    [0, 3, 0, 4],
    [10, 20, 30, 40],
    [1, 1, 1, 1, 1, 1, 1],
]


def test_shares_always_add_up_to_the_total():
    for total in range(0, 130):
        for ratios in RATIOS:
            assert sum(split_by_ratio(total, ratios)) == total


def test_each_share_is_its_exact_proportion_rounded_down_or_up():
    for total in range(0, 130):
        for ratios in RATIOS:
            whole = sum(ratios)
            for share, ratio in zip(split_by_ratio(total, ratios), ratios, strict=True):
                floor = total * ratio // whole
                assert floor <= share <= floor + 1


def test_the_left_over_cents_go_to_the_largest_remainders_with_ties_to_the_earlier_share():
    for total in range(0, 130):
        for ratios in RATIOS:
            whole = sum(ratios)
            shares = split_by_ratio(total, ratios)
            floors = [total * r // whole for r in ratios]
            rems = [total * r % whole for r in ratios]
            got = [i for i in range(len(ratios)) if shares[i] == floors[i] + 1]
            ranked = sorted(range(len(ratios)), key=lambda i: (-rems[i], i))
            assert got == sorted(ranked[: total - sum(floors)])


def test_pairs_and_triples_of_small_ratios():
    for ratios in itertools.chain(
        itertools.product(range(0, 5), repeat=2), itertools.product(range(0, 4), repeat=3)
    ):
        if sum(ratios) == 0:
            continue
        for total in range(0, 25):
            shares = split_by_ratio(total, list(ratios))
            assert sum(shares) == total
            assert all(s >= 0 for s in shares)
            assert all(s == 0 for s, r in zip(shares, ratios, strict=True) if r == 0)
