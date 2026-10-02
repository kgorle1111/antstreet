from shortestpath import shortest_path

GRAPH = {
    "A": {"B": 7, "C": 9, "F": 14},
    "B": {"A": 7, "C": 10, "D": 15},
    "C": {"A": 9, "B": 10, "D": 11, "F": 2},
    "D": {"B": 15, "C": 11, "E": 6},
    "E": {"D": 6, "F": 9},
    "F": {"A": 14, "C": 2, "E": 9},
}


def test_classic_graph():
    assert shortest_path(GRAPH, "A", "E") == (20, ["A", "C", "F", "E"])
    assert shortest_path(GRAPH, "A", "D") == (20, ["A", "C", "D"])
    assert shortest_path(GRAPH, "B", "F") == (12, ["B", "C", "F"])


def test_single_edge_and_two_hop_path():
    graph = {"a": {"b": 3}, "b": {"c": 4}}
    assert shortest_path(graph, "a", "b") == (3, ["a", "b"])
    assert shortest_path(graph, "a", "c") == (7, ["a", "b", "c"])


def test_the_returned_value_is_a_tuple_with_a_list_path():
    result = shortest_path({"a": {"b": 1}}, "a", "b")
    assert isinstance(result, tuple)
    total, path = result
    assert total == 1
    assert isinstance(path, list)


def test_source_equals_target():
    assert shortest_path({"a": {"b": 1}}, "a", "a") == (0, ["a"])
    assert shortest_path({"a": {}}, "a", "a") == (0, ["a"])
    assert shortest_path({"a": {"b": 1}}, "b", "b") == (0, ["b"])
    assert shortest_path({"a": {"a": 5}}, "a", "a") == (0, ["a"])


def test_a_longer_route_with_smaller_total_beats_a_direct_edge():
    graph = {"a": {"b": 10, "c": 1}, "c": {"d": 1}, "d": {"b": 1}}
    assert shortest_path(graph, "a", "b") == (3, ["a", "c", "d", "b"])


def test_edges_are_directed():
    graph = {"a": {"b": 1}, "b": {"c": 1}, "c": {}}
    assert shortest_path(graph, "a", "c") == (2, ["a", "b", "c"])
    assert shortest_path(graph, "c", "a") is None
    assert shortest_path(graph, "b", "a") is None


def test_float_weights():
    graph = {"a": {"b": 0.5, "c": 2.0}, "b": {"c": 1.25}}
    total, path = shortest_path(graph, "a", "c")
    assert total == 1.75
    assert path == ["a", "b", "c"]


def test_numeric_and_tuple_nodes():
    graph = {1: {2: 1, 3: 5}, 2: {3: 1}, 3: {(4, 4): 2}}
    assert shortest_path(graph, 1, (4, 4)) == (4, [1, 2, 3, (4, 4)])


def test_self_loops_and_cycles_do_not_confuse_it():
    graph = {"a": {"a": 1, "b": 2}, "b": {"a": 1, "c": 3}, "c": {"b": 1}}
    assert shortest_path(graph, "a", "c") == (5, ["a", "b", "c"])
    assert shortest_path(graph, "c", "a") == (2, ["c", "b", "a"])
