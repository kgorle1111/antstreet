from toposort import toposort


def test_chain():
    assert toposort({"c": ["b"], "b": ["a"], "a": []}) == ["a", "b", "c"]


def test_diamond():
    graph = {"d": ["b", "c"], "b": ["a"], "c": ["a"], "a": []}
    assert toposort(graph) == ["a", "b", "c", "d"]


def test_empty_and_single():
    assert toposort({}) == []
    assert toposort({"x": []}) == ["x"]


def test_independent_nodes_come_out_sorted():
    assert toposort({"b": [], "c": [], "a": []}) == ["a", "b", "c"]
    assert toposort({3: [], 1: [], 2: []}) == [1, 2, 3]


def test_returns_a_list():
    assert isinstance(toposort({"a": ["b"]}), list)
