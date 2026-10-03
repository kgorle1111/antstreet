import copy
import random

from knapsack import knapsack


def best_value_only(items, capacity):
    table = [0] * (capacity + 1)
    for weight, value in items:
        for room in range(capacity, weight - 1, -1):
            table[room] = max(table[room], table[room - weight] + value)
    return table[capacity]


def test_two_hundred_items_and_a_capacity_of_five_thousand():
    rng = random.Random(10)
    items = [(rng.randint(1, 400), rng.randint(0, 1000)) for _ in range(200)]
    best, chosen = knapsack(items, 5000)
    assert best == best_value_only(items, 5000)
    assert chosen == sorted(set(chosen))
    assert sum(items[i][0] for i in chosen) <= 5000
    assert sum(items[i][1] for i in chosen) == best


def test_a_large_capacity_with_few_items():
    items = [(40_000, 5), (30_000, 4), (35_000, 7)]
    assert knapsack(items, 70_000) == (11, [1, 2])


def test_the_input_is_not_changed():
    items = [(5, 10), (4, 40), (6, 30), (3, 50)]
    before = copy.deepcopy(items)
    knapsack(items, 10)
    assert items == before
