import pytest
from knapsack import knapsack


@pytest.mark.parametrize(
    ("items", "capacity", "expected"),
    [
        ([(5, 10), (4, 40), (6, 30), (3, 50)], 10, (90, [1, 3])),
        ([(1, 1), (3, 4), (4, 5), (5, 7)], 7, (9, [1, 2])),
        ([(10, 60), (20, 100), (30, 120)], 50, (220, [1, 2])),
        ([(12, 4), (2, 2), (1, 1), (1, 2), (4, 10)], 15, (15, [1, 2, 3, 4])),
        ([(1, 5)], 1, (5, [0])),
        ([(2, 3), (3, 4), (4, 5), (5, 6)], 5, (7, [0, 1])),
        ([(3, 4), (2, 3), (4, 6)], 6, (9, [1, 2])),
    ],
)
def test_known_answers(items, capacity, expected):
    assert knapsack(items, capacity) == expected


def test_a_value_dense_item_is_not_always_best_greedy_fails_here():
    # by value per weight the first item looks best, but the other two together are worth more
    assert knapsack([(6, 12), (5, 9), (5, 9)], 10) == (18, [1, 2])
    assert knapsack([(1, 2), (10, 20), (10, 19)], 10) == (20, [1])


def test_everything_fits():
    assert knapsack([(1, 1), (2, 2), (3, 3)], 100) == (6, [0, 1, 2])


def test_the_result_is_a_tuple_with_a_list_of_plain_ints():
    best, chosen = knapsack([(1, 1), (2, 5)], 2)
    assert type(best) is int
    assert isinstance(chosen, list) and all(type(i) is int for i in chosen)
    assert isinstance(knapsack([(1, 1)], 1), tuple)


def test_tuples_and_lists_are_both_fine():
    assert knapsack(((5, 10), (4, 40), (6, 30), (3, 50)), 10) == (90, [1, 3])
    assert knapsack([[5, 10], [4, 40], [6, 30], [3, 50]], 10) == (90, [1, 3])
