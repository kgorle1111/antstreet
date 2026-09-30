import random

from toposort import toposort


def test_not_a_layer_by_layer_order():
    assert toposort({"a": [], "c": [], "b": ["a"]}) == ["a", "b", "c"]
    assert toposort({"b": [], "a": ["b"], "c": []}) == ["b", "a", "c"]


def test_ints():
    assert toposort({3: [1], 1: [], 2: []}) == [1, 2, 3]
    assert toposort({5: [], 4: [5], 1: [4], 2: []}) == [2, 5, 4, 1]


def test_smallest_ready_node_wins_after_each_step():
    graph = {"z": [], "y": ["z"], "m": [], "a": ["m"], "k": ["a", "y"]}
    assert toposort(graph) == ["m", "a", "z", "y", "k"]


def test_result_ignores_insertion_order():
    graph = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"], "e": [], "f": ["e", "d"]}
    expected = toposort(graph)
    items = list(graph.items())
    rng = random.Random(7)
    for _ in range(20):
        rng.shuffle(items)
        shuffled = {node: rng.sample(deps, len(deps)) for node, deps in items}
        assert toposort(shuffled) == expected
