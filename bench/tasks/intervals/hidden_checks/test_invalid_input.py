import pytest
from intervals import merge, subtract, total_length


@pytest.mark.parametrize("bad", [[(5, 3)], [(1, 2), (9, 4)], [(0, 10), (5, 3)], [(-1, -2)]])
def test_merge_rejects_start_after_end(bad):
    with pytest.raises(ValueError):
        merge(bad)


@pytest.mark.parametrize("bad", [[(5, 3)], [(0, 10), (5, 3)], [(1, 2), (4, 3)]])
def test_total_length_rejects_start_after_end(bad):
    with pytest.raises(ValueError):
        total_length(bad)


def test_subtract_rejects_start_after_end_in_either_argument():
    with pytest.raises(ValueError):
        subtract([(5, 3)], [(1, 2)])
    with pytest.raises(ValueError):
        subtract([(0, 10)], [(5, 3)])


def test_invalid_interval_is_rejected_even_when_redundant_or_ignored():
    with pytest.raises(ValueError):
        subtract([(0, 10), (12, 11)], [])
    with pytest.raises(ValueError):
        subtract([], [(5, 3)])
    with pytest.raises(ValueError):
        subtract([(20, 30)], [(0, 10), (8, 4)])
