from moneysplit import split_by_ratio, split_even


def test_amounts_beyond_float_precision_are_exact():
    assert split_by_ratio(10**20, [1, 2]) == [33333333333333333333, 66666666666666666667]
    assert split_even(10**20, 3) == [
        33333333333333333334,
        33333333333333333333,
        33333333333333333333,
    ]
    assert split_even(2**64 + 1, 2) == [2**63 + 1, 2**63]
    assert split_by_ratio(10**30 + 1, [1, 1]) == [10**30 // 2 + 1, 10**30 // 2]


def test_huge_ratios_are_exact_too():
    assert split_by_ratio(10**18, [10**18, 10**18]) == [5 * 10**17, 5 * 10**17]
    assert split_by_ratio(10, [10**30, 2 * 10**30]) == [3, 7]
    assert split_by_ratio(100, [10**25 + 1, 10**25 + 1, 10**25 + 1]) == [34, 33, 33]


def test_shares_add_up_and_stay_within_one_cent_of_the_exact_share():
    for total in (10**15 + 7, 10**18 - 1, 2**70 + 3, 123456789012345678901234567890):
        for ratios in ([1, 2, 3], [7, 7, 7, 7], [1, 10**9, 3], [0, 5, 11]):
            shares = split_by_ratio(total, ratios)
            assert sum(shares) == total
            whole = sum(ratios)
            for share, ratio in zip(shares, ratios, strict=True):
                floor = total * ratio // whole
                assert floor <= share <= floor + 1
