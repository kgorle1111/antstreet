from rangesum import RangeSum


def test_update_adds_to_one_element():
    rs = RangeSum([1, 2, 3, 4])
    rs.update(2, 10)
    assert rs.get(2) == 13
    assert [rs.get(i) for i in (0, 1, 3)] == [1, 2, 4]
    assert rs.prefix(4) == 20
    assert rs.range_sum(2, 3) == 13
    assert rs.range_sum(0, 2) == 3


def test_update_with_negative_and_zero_delta():
    rs = RangeSum([5, 5, 5])
    rs.update(1, -7)
    assert rs.get(1) == -2
    assert rs.prefix(3) == 8
    rs.update(1, 0)
    assert rs.get(1) == -2
    assert rs.prefix(3) == 8


def test_set_replaces_the_value():
    rs = RangeSum([1, 2, 3, 4])
    rs.set(1, 20)
    assert rs.get(1) == 20
    assert rs.prefix(4) == 28
    rs.set(1, -3)
    assert rs.get(1) == -3
    assert rs.prefix(4) == 5
    rs.set(1, -3)
    assert rs.prefix(4) == 5


def test_updates_to_every_position_including_the_last():
    values = [1] * 8
    rs = RangeSum(list(values))
    for i in range(8):
        rs.update(i, i + 1)
        values[i] += i + 1
        assert rs.prefix(8) == sum(values)
        assert rs.range_sum(i, 8) == sum(values[i:])
        assert rs.get(i) == values[i]


def test_update_at_each_end_of_a_power_of_two_and_a_non_power_of_two_length():
    for n in (1, 2, 7, 8, 9, 16, 17):
        rs = RangeSum([0] * n)
        rs.update(0, 3)
        rs.update(n - 1, 5)
        last = 5 if n > 1 else 8
        assert rs.prefix(n) == 8
        assert rs.range_sum(0, n) == 8
        assert rs.range_sum(n - 1, n) == last


def test_repeated_updates_accumulate():
    rs = RangeSum([0, 0, 0])
    for _ in range(100):
        rs.update(1, 2)
    assert rs.get(1) == 200
    assert rs.prefix(3) == 200
    assert rs.range_sum(0, 1) == 0


def test_set_then_update_then_set():
    rs = RangeSum([10, 20, 30])
    rs.set(0, 1)
    rs.update(0, 1)
    rs.set(2, rs.get(0) + rs.get(1))
    assert [rs.get(i) for i in range(3)] == [2, 20, 22]
    assert rs.prefix(3) == 44
