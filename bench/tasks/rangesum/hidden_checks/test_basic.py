from rangesum import RangeSum

VALUES = [5, 3, 8, 6, 2, 7, 4, 1]


def test_len_and_get():
    rs = RangeSum(VALUES)
    assert len(rs) == 8
    assert [rs.get(i) for i in range(8)] == VALUES


def test_prefix_sums():
    rs = RangeSum(VALUES)
    assert rs.prefix(0) == 0
    assert rs.prefix(1) == 5
    assert rs.prefix(3) == 16
    assert rs.prefix(8) == 36
    for n in range(9):
        assert rs.prefix(n) == sum(VALUES[:n])


def test_range_sums_are_half_open():
    rs = RangeSum(VALUES)
    assert rs.range_sum(0, 8) == 36
    assert rs.range_sum(0, 1) == 5
    assert rs.range_sum(2, 5) == 8 + 6 + 2
    assert rs.range_sum(7, 8) == 1
    assert rs.range_sum(3, 4) == 6


def test_every_range_matches_a_plain_sum():
    values = [4, -9, 0, 17, -3, 8, 8, -1, 2]
    rs = RangeSum(values)
    for lo in range(len(values) + 1):
        for hi in range(lo, len(values) + 1):
            assert rs.range_sum(lo, hi) == sum(values[lo:hi]), (lo, hi)


def test_accepts_any_iterable_and_a_single_element():
    assert RangeSum(iter([1, 2, 3])).prefix(3) == 6
    assert RangeSum(x * x for x in range(5)).range_sum(1, 4) == 1 + 4 + 9
    one = RangeSum([42])
    assert len(one) == 1
    assert one.get(0) == 42
    assert one.range_sum(0, 1) == 42
    assert one.prefix(1) == 42


def test_negative_and_zero_values():
    rs = RangeSum([-5, 0, 5, -10, 0])
    assert rs.prefix(5) == -10
    assert rs.range_sum(0, 3) == 0
    assert rs.range_sum(3, 5) == -10
    assert rs.get(1) == 0


def test_large_integers_stay_exact():
    big = 10**30
    rs = RangeSum([big, 1, big])
    assert rs.prefix(3) == 2 * big + 1
    assert rs.range_sum(1, 3) == big + 1
