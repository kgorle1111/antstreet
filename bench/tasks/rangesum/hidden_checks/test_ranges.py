from rangesum import RangeSum

VALUES = [3, 1, 4, 1, 5, 9, 2, 6]


def test_hi_is_excluded_and_lo_is_included():
    rs = RangeSum(VALUES)
    assert rs.range_sum(1, 3) == 1 + 4
    assert rs.range_sum(1, 2) == 1
    assert rs.range_sum(5, 6) == 9


def test_empty_ranges_are_zero_everywhere_including_both_ends():
    rs = RangeSum(VALUES)
    for k in range(len(VALUES) + 1):
        assert rs.range_sum(k, k) == 0


def test_range_ending_at_len_is_valid():
    rs = RangeSum(VALUES)
    assert rs.range_sum(4, 8) == 5 + 9 + 2 + 6
    assert rs.range_sum(8, 8) == 0
    assert rs.range_sum(0, 8) == sum(VALUES)


def test_range_sum_equals_difference_of_prefixes():
    rs = RangeSum(VALUES)
    for lo in range(9):
        for hi in range(lo, 9):
            assert rs.range_sum(lo, hi) == rs.prefix(hi) - rs.prefix(lo)


def test_ranges_after_updates_see_the_new_values():
    rs = RangeSum(list(VALUES))
    rs.update(4, 100)
    assert rs.range_sum(4, 5) == 105
    assert rs.range_sum(0, 4) == 9
    assert rs.range_sum(5, 8) == 17
    assert rs.range_sum(3, 6) == 1 + 105 + 9


def test_empty_sequence_has_only_empty_ranges():
    rs = RangeSum()
    assert len(rs) == 0
    assert rs.prefix(0) == 0
    assert rs.range_sum(0, 0) == 0
    assert RangeSum([]).range_sum(0, 0) == 0
