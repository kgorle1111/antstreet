import copy

from toposort import layers, toposort


def make_graph():
    return {"d": ["b", "c", "ghost"], "b": ["a", "a"], "c": {"a"}, "a": (), "e": []}


def test_toposort_leaves_input_unchanged():
    graph = make_graph()
    snapshot = copy.deepcopy(graph)
    toposort(graph)
    assert graph == snapshot
    assert list(graph) == list(snapshot)
    assert "ghost" not in graph


def test_layers_leaves_input_unchanged():
    graph = make_graph()
    snapshot = copy.deepcopy(graph)
    layers(graph)
    assert graph == snapshot
    assert list(graph) == list(snapshot)
    assert "ghost" not in graph


def test_dependency_lists_keep_order_and_length():
    graph = {"c": ["b", "a", "b"], "b": ["a"], "a": []}
    toposort(graph)
    layers(graph)
    assert graph["c"] == ["b", "a", "b"]
    assert graph["b"] == ["a"]


def test_repeated_calls_give_the_same_answer():
    graph = make_graph()
    assert toposort(graph) == toposort(graph)
    assert layers(graph) == layers(graph)


def test_result_is_a_fresh_list():
    graph = {"a": []}
    first = toposort(graph)
    first.append("junk")
    assert toposort(graph) == ["a"]
