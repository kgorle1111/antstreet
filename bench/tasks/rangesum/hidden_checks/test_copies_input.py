from rangesum import RangeSum


def test_changing_the_source_list_afterwards_does_not_affect_it():
    source = [1, 2, 3, 4]
    rs = RangeSum(source)
    source[0] = 100
    source.append(5)
    source.clear()
    assert len(rs) == 4
    assert rs.get(0) == 1
    assert rs.prefix(4) == 10


def test_it_never_changes_the_list_it_was_given():
    source = [1, 2, 3, 4]
    rs = RangeSum(source)
    rs.update(0, 10)
    rs.set(3, 0)
    assert source == [1, 2, 3, 4]
    assert rs.get(0) == 11
    assert rs.get(3) == 0


def test_two_instances_from_one_list_are_independent():
    source = [1, 2, 3]
    a = RangeSum(source)
    b = RangeSum(source)
    a.update(0, 5)
    assert b.get(0) == 1
    assert b.prefix(3) == 6
    assert a.prefix(3) == 11


def test_a_tuple_and_a_range_work_too():
    assert RangeSum((1, 2, 3)).prefix(3) == 6
    assert RangeSum(range(5)).range_sum(2, 5) == 2 + 3 + 4
