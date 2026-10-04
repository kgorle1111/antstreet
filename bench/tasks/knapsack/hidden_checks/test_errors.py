import pytest
from knapsack import knapsack

OK = [(1, 2), (2, 3)]


@pytest.mark.parametrize("bad", [None, 5, "12", {1: 2}, {(1, 2)}, 1.5])
def test_items_that_are_not_a_list_raise_type_error(bad):
    with pytest.raises(TypeError):
        knapsack(bad, 5)


@pytest.mark.parametrize("bad", [(1,), (1, 2, 3), (), 5, "ab", None, {1, 2}, {1: 2, 3: 4}])
def test_an_item_that_is_not_a_pair_raises_value_error(bad):
    with pytest.raises(ValueError):
        knapsack([bad], 5)
    with pytest.raises(ValueError):
        knapsack([*OK, bad], 5)


@pytest.mark.parametrize("bad", [1.0, "1", None, True, False, [1], 2.5])
def test_a_weight_or_value_that_is_not_an_int_raises_type_error(bad):
    with pytest.raises(TypeError):
        knapsack([(bad, 2)], 5)
    with pytest.raises(TypeError):
        knapsack([(1, bad)], 5)
    with pytest.raises(TypeError):
        knapsack([*OK, (3, bad)], 5)


@pytest.mark.parametrize("bad", [1.0, "5", None, True, 2.5, [5]])
def test_a_capacity_that_is_not_an_int_raises_type_error(bad):
    with pytest.raises(TypeError):
        knapsack(OK, bad)
    with pytest.raises(TypeError):
        knapsack([], bad)


@pytest.mark.parametrize("weight", [0, -1, -100])
def test_a_weight_below_one_raises_value_error(weight):
    with pytest.raises(ValueError):
        knapsack([(weight, 5)], 10)
    with pytest.raises(ValueError):
        knapsack([*OK, (weight, 5)], 10)


@pytest.mark.parametrize("value", [-1, -100])
def test_a_negative_value_raises_value_error(value):
    with pytest.raises(ValueError):
        knapsack([(1, value)], 10)


@pytest.mark.parametrize("capacity", [-1, -100])
def test_a_negative_capacity_raises_value_error(capacity):
    with pytest.raises(ValueError):
        knapsack(OK, capacity)
    with pytest.raises(ValueError):
        knapsack([], capacity)


def test_every_item_is_checked_even_one_that_could_never_be_taken():
    with pytest.raises(ValueError):
        knapsack([(1, 1), (999, -1)], 5)
    with pytest.raises(ValueError):
        knapsack([(1, 1), (0, 5)], 0)
    with pytest.raises(TypeError):
        knapsack([(1, 1), (999, 1.5)], 5)


def test_a_value_of_zero_and_a_weight_of_one_are_valid():
    assert knapsack([(1, 0)], 1) == (0, [])
    assert knapsack([(1, 1)], 0) == (0, [])
