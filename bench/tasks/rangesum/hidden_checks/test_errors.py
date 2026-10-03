import pytest
from rangesum import RangeSum


def make():
    return RangeSum([1, 2, 3, 4])


@pytest.mark.parametrize("i", [4, 5, 100, -1, -4, -5])
def test_get_set_update_reject_out_of_range_positions(i):
    rs = make()
    with pytest.raises(IndexError):
        rs.get(i)
    with pytest.raises(IndexError):
        rs.set(i, 9)
    with pytest.raises(IndexError):
        rs.update(i, 9)
    assert [rs.get(k) for k in range(4)] == [1, 2, 3, 4]
    assert rs.prefix(4) == 10


@pytest.mark.parametrize("n", [5, 6, 100, -1, -4])
def test_prefix_rejects_out_of_range_lengths(n):
    with pytest.raises(IndexError):
        make().prefix(n)


@pytest.mark.parametrize("lo,hi", [(-1, 2), (0, 5), (-1, 5), (4, 5), (-3, 0), (5, 5), (-2, -1)])
def test_range_sum_rejects_out_of_range_bounds(lo, hi):
    with pytest.raises(IndexError):
        make().range_sum(lo, hi)


@pytest.mark.parametrize("lo,hi", [(3, 2), (4, 0), (1, 0), (2, 1)])
def test_range_sum_with_lo_greater_than_hi_raises_value_error(lo, hi):
    with pytest.raises(ValueError):
        make().range_sum(lo, hi)


def test_lo_greater_than_hi_wins_over_out_of_range():
    rs = make()
    with pytest.raises(ValueError):
        rs.range_sum(9, 8)
    with pytest.raises(ValueError):
        rs.range_sum(0, -1)
    with pytest.raises(ValueError):
        rs.range_sum(3, -5)


@pytest.mark.parametrize("bad", [1.0, 1.5, "1", None, [1]])
def test_non_int_arguments_raise_type_error(bad):
    rs = make()
    with pytest.raises(TypeError):
        rs.get(bad)
    with pytest.raises(TypeError):
        rs.set(bad, 1)
    with pytest.raises(TypeError):
        rs.update(bad, 1)
    with pytest.raises(TypeError):
        rs.prefix(bad)
    with pytest.raises(TypeError):
        rs.range_sum(bad, 3)
    with pytest.raises(TypeError):
        rs.range_sum(0, bad)


def test_type_error_wins_over_the_other_errors():
    rs = make()
    with pytest.raises(TypeError):
        rs.range_sum(3.0, 1)
    with pytest.raises(TypeError):
        rs.range_sum(1, 99.0)
    with pytest.raises(TypeError):
        rs.get(99.0)


def test_empty_sequence_has_no_valid_positions():
    rs = RangeSum()
    for call in (lambda: rs.get(0), lambda: rs.set(0, 1), lambda: rs.update(0, 1)):
        with pytest.raises(IndexError):
            call()
    with pytest.raises(IndexError):
        rs.prefix(1)
    with pytest.raises(IndexError):
        rs.range_sum(0, 1)


def test_failed_calls_leave_the_contents_unchanged():
    rs = make()
    for call in (
        lambda: rs.update(7, 5),
        lambda: rs.set(-1, 5),
        lambda: rs.range_sum(3, 1),
        lambda: rs.prefix(9),
    ):
        with pytest.raises((IndexError, ValueError)):
            call()
    assert [rs.get(i) for i in range(4)] == [1, 2, 3, 4]
    assert rs.prefix(4) == 10
    assert len(rs) == 4
