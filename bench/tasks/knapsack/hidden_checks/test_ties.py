import pytest
from knapsack import knapsack


def test_the_lighter_choice_wins_a_value_tie():
    assert knapsack([(2, 3), (3, 3)], 3) == (3, [0])
    assert knapsack([(3, 3), (2, 3)], 3) == (3, [1])
    assert knapsack([(5, 10), (2, 10), (4, 10)], 5) == (10, [1])


def test_a_lighter_set_of_several_items_beats_one_heavy_item():
    # {0, 1} and {2} are both worth 10; the pair weighs 5 and the single item weighs 6
    assert knapsack([(2, 4), (3, 6), (6, 10)], 6) == (10, [0, 1])
    assert knapsack([(6, 10), (2, 4), (3, 6)], 6) == (10, [1, 2])


def test_equal_value_and_weight_the_smaller_list_of_positions_wins():
    assert knapsack([(1, 1), (1, 1), (2, 2)], 2) == (2, [0, 1])
    assert knapsack([(2, 2), (1, 1), (1, 1)], 2) == (2, [0])
    assert knapsack([(2, 3), (2, 3)], 2) == (3, [0])
    assert knapsack([(2, 3), (2, 3), (2, 3)], 4) == (6, [0, 1])


def test_the_first_position_that_differs_decides():
    # four pairs are worth 3 and weigh 3: [0, 1], [0, 2], [1, 3] and [2, 3]
    assert knapsack([(1, 1), (2, 2), (2, 2), (1, 1)], 3) == (3, [0, 1])
    assert knapsack([(2, 2), (1, 1), (1, 1), (2, 2)], 3) == (3, [0, 1])
    assert knapsack([(1, 5), (2, 5), (2, 5), (1, 5)], 3) == (10, [0, 3])
    assert knapsack([(3, 7), (1, 2), (2, 5), (1, 4), (1, 3)], 4) == (12, [2, 3, 4])


def test_lower_positions_win_among_three_way_ties():
    items = [(1, 1)] * 5
    assert knapsack(items, 3) == (3, [0, 1, 2])
    assert knapsack(items, 1) == (1, [0])
    items = [(2, 4), (1, 2), (1, 2), (1, 2), (2, 4)]
    assert knapsack(items, 2) == (4, [0])


def test_weight_before_positions_and_value_before_weight():
    # same value 10: {1} weighs 2 and {0} weighs 3, so position 1 wins despite the higher index
    assert knapsack([(3, 10), (2, 10)], 3) == (10, [1])
    # a heavier choice with more value still wins over a lighter one
    assert knapsack([(1, 1), (4, 11)], 4) == (11, [1])


@pytest.mark.parametrize("zero_value_items", [[(1, 0)], [(1, 0), (2, 0), (3, 0)], [(5, 0), (1, 0)]])
def test_items_worth_nothing_are_never_taken(zero_value_items):
    assert knapsack(zero_value_items, 10) == (0, [])
    assert knapsack([(2, 3), *zero_value_items], 10) == (3, [0])
    assert knapsack([*zero_value_items, (2, 3)], 10) == (3, [len(zero_value_items)])
