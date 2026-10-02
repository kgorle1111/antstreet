import pytest
from moneysplit import split_by_ratio, split_even


@pytest.mark.parametrize("total", [1.5, 100.0, "100", None, [100], True, False])
def test_total_that_is_not_an_int_is_a_type_error(total):
    with pytest.raises(TypeError):
        split_by_ratio(total, [1, 2])
    with pytest.raises(TypeError):
        split_even(total, 3)


@pytest.mark.parametrize("parts", [2.0, 2.5, "3", None, True, [3]])
def test_parts_that_is_not_an_int_is_a_type_error(parts):
    with pytest.raises(TypeError):
        split_even(100, parts)


@pytest.mark.parametrize(
    "ratios", [[1.0, 2], [1, "2"], [None, 1], [True, 1], [1, 2.5], ["12"], [[1], 2]]
)
def test_a_ratio_that_is_not_an_int_is_a_type_error(ratios):
    with pytest.raises(TypeError):
        split_by_ratio(100, ratios)


@pytest.mark.parametrize("ratios", [3, None, 2.5])
def test_ratios_that_is_not_iterable_is_a_type_error(ratios):
    with pytest.raises(TypeError):
        split_by_ratio(100, ratios)


@pytest.mark.parametrize("parts", [0, -1, -10])
def test_parts_below_one_is_a_value_error(parts):
    with pytest.raises(ValueError):
        split_even(100, parts)
    with pytest.raises(ValueError):
        split_even(0, parts)


@pytest.mark.parametrize("make", [list, tuple, iter])
def test_empty_ratios_is_a_value_error(make):
    with pytest.raises(ValueError):
        split_by_ratio(100, make([]))


@pytest.mark.parametrize("ratios", [[-1, 2], [1, -1], [3, -1, 3], [-1], [-1, 1]])
def test_a_negative_ratio_is_a_value_error(ratios):
    with pytest.raises(ValueError):
        split_by_ratio(100, ratios)


@pytest.mark.parametrize("ratios", [[0], [0, 0], [0, 0, 0]])
def test_ratios_adding_up_to_zero_is_a_value_error(ratios):
    with pytest.raises(ValueError):
        split_by_ratio(100, ratios)
    with pytest.raises(ValueError):
        split_by_ratio(0, ratios)


def test_valid_calls_still_work_after_the_errors():
    assert split_even(7, 1) == [7]
    assert split_by_ratio(100, [1]) == [100]
