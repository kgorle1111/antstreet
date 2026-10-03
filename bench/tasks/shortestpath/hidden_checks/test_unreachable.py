from shortestpath import distances, shortest_path


def test_target_in_another_component_gives_none():
    graph = {"a": {"b": 1}, "c": {"d": 1}}
    assert shortest_path(graph, "a", "d") is None
    assert shortest_path(graph, "a", "c") is None
    assert shortest_path(graph, "c", "b") is None


def test_unreachable_is_none_not_an_infinite_total():
    result = shortest_path({"a": {}, "b": {}}, "a", "b")
    assert result is None


def test_a_node_that_only_appears_as_a_neighbour_is_reachable_but_leads_nowhere():
    graph = {"a": {"b": 2}}
    assert shortest_path(graph, "a", "b") == (2, ["a", "b"])
    assert shortest_path(graph, "b", "a") is None
    assert shortest_path(graph, "b", "b") == (0, ["b"])


def test_distances_leave_out_unreachable_nodes():
    graph = {"a": {"b": 1}, "b": {"c": 2}, "x": {"a": 1}, "y": {}}
    assert distances(graph, "a") == {"a": 0, "b": 1, "c": 3}
    assert distances(graph, "x") == {"x": 0, "a": 1, "b": 2, "c": 4}
    assert distances(graph, "y") == {"y": 0}


def test_an_edge_pointing_back_to_the_source_does_not_matter():
    graph = {"a": {"b": 1}, "b": {"a": 1, "c": 1}}
    assert distances(graph, "a") == {"a": 0, "b": 1, "c": 2}
    assert shortest_path(graph, "c", "a") is None


def test_a_dead_end_branch_is_not_taken():
    graph = {"s": {"dead": 1, "t": 5}, "dead": {}}
    assert shortest_path(graph, "s", "t") == (5, ["s", "t"])
    assert shortest_path(graph, "s", "dead") == (1, ["s", "dead"])


def test_empty_edge_dicts_everywhere():
    graph = {"a": {}, "b": {}, "c": {}}
    assert distances(graph, "b") == {"b": 0}
    assert shortest_path(graph, "b", "b") == (0, ["b"])
    assert shortest_path(graph, "a", "c") is None
