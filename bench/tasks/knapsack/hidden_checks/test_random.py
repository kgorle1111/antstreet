import random
from itertools import combinations

from knapsack import knapsack


def brute_force(items, capacity):
    """Every subset, scored by (value high, weight low, positions low)."""
    best_key, best_set = None, None
    for size in range(len(items) + 1):
        for subset in combinations(range(len(items)), size):
            weight = sum(items[i][0] for i in subset)
            if weight > capacity:
                continue
            value = sum(items[i][1] for i in subset)
            key = (-value, weight, list(subset))
            if best_key is None or key < best_key:
                best_key, best_set = key, subset
    return -best_key[0], list(best_set)


def test_small_instances_against_every_subset():
    rng = random.Random(2024)
    for _ in range(400):
        n = rng.randint(0, 9)
        items = [(rng.randint(1, 6), rng.randint(0, 8)) for _ in range(n)]
        capacity = rng.randint(0, 20)
        assert knapsack(items, capacity) == brute_force(items, capacity), (items, capacity)


def test_many_equal_items_make_many_ties():
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(1, 10)
        items = [(rng.choice([1, 2]), rng.choice([1, 2])) for _ in range(n)]
        capacity = rng.randint(1, 8)
        assert knapsack(items, capacity) == brute_force(items, capacity), (items, capacity)


def test_the_answer_is_consistent_with_its_own_items():
    rng = random.Random(5)
    for _ in range(100):
        items = [(rng.randint(1, 30), rng.randint(0, 50)) for _ in range(rng.randint(0, 40))]
        capacity = rng.randint(0, 120)
        best, chosen = knapsack(items, capacity)
        assert chosen == sorted(set(chosen))
        assert all(0 <= i < len(items) for i in chosen)
        assert sum(items[i][0] for i in chosen) <= capacity
        assert sum(items[i][1] for i in chosen) == best
