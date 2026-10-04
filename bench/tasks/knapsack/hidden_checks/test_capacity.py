from knapsack import knapsack


def test_zero_capacity_takes_nothing():
    assert knapsack([(1, 5), (2, 9)], 0) == (0, [])
    assert knapsack([], 0) == (0, [])


def test_no_items():
    assert knapsack([], 10) == (0, [])
    assert knapsack((), 10) == (0, [])


def test_an_item_that_exactly_fills_the_bag_fits():
    assert knapsack([(5, 7)], 5) == (7, [0])
    assert knapsack([(2, 3), (3, 4)], 5) == (7, [0, 1])
    assert knapsack([(4, 9), (1, 1)], 4) == (9, [0])


def test_one_unit_short_leaves_the_item_out():
    assert knapsack([(5, 7)], 4) == (0, [])
    assert knapsack([(2, 3), (3, 4)], 4) == (4, [1])


def test_an_item_heavier_than_the_capacity_is_never_taken():
    assert knapsack([(100, 1000), (1, 1)], 10) == (1, [1])
    assert knapsack([(11, 5), (10, 5), (12, 5)], 10) == (5, [1])
    assert knapsack([(6, 6), (50, 999)], 5) == (0, [])


def test_large_weights_and_values_are_handled_exactly():
    big = 10**15
    assert knapsack([(3, big), (4, big + 1), (5, 2 * big)], 8) == (3 * big, [0, 2])
    assert knapsack([(1, 10**30)], 1) == (10**30, [0])


def test_capacity_much_larger_than_the_weights():
    assert knapsack([(1, 1), (2, 3)], 1000) == (4, [0, 1])
