import pytest
from shortestpath import distances

GRAPH = {
    "A": {"B": 7, "C": 9, "F": 14},
    "B": {"A": 7, "C": 10, "D": 15},
    "C": {"A": 9, "B": 10, "D": 11, "F": 2},
    "D": {"B": 15, "C": 11, "E": 6},
    "E": {"D": 6, "F": 9},
    "F": {"A": 14, "C": 2, "E": 9},
}


def test_distances_on_the_classic_graph():
    assert distances(GRAPH, "A") == {"A": 0, "B": 7, "C": 9, "D": 20, "E": 20, "F": 11}
    assert distances(GRAPH, "E") == {"E": 0, "D": 6, "F": 9, "C": 11, "A": 20, "B": 21}


def test_source_is_included_at_zero():
    assert distances({"a": {"b": 1}}, "a")["a"] == 0
    assert distances({"a": {}}, "a") == {"a": 0}


def test_a_neighbour_only_node_has_an_entry_when_reachable():
    assert distances({"a": {"b": 4}}, "a") == {"a": 0, "b": 4}


def test_cheaper_indirect_route_wins():
    graph = {"a": {"b": 10, "c": 2}, "c": {"b": 3}}
    assert distances(graph, "a") == {"a": 0, "c": 2, "b": 5}


def test_a_cycle_back_to_the_source_keeps_the_source_at_zero():
    graph = {"a": {"b": 1}, "b": {"a": 1}}
    assert distances(graph, "a") == {"a": 0, "b": 1}
    assert distances(graph, "b") == {"b": 0, "a": 1}


def test_float_distances():
    graph = {"a": {"b": 0.25}, "b": {"c": 0.5}}
    assert distances(graph, "a") == {"a": 0, "b": 0.25, "c": 0.75}


def test_distances_are_consistent_with_every_edge():
    result = distances(GRAPH, "B")
    assert set(result) == set(GRAPH)
    for node, edges in GRAPH.items():
        for nxt, weight in edges.items():
            assert result[nxt] <= result[node] + weight


def test_unknown_source_raises_key_error():
    with pytest.raises(KeyError):
        distances(GRAPH, "Q")
