import pytest
from shortestpath import distances, shortest_path

GRAPH = {"a": {"b": 1}, "b": {"c": 1}}


def test_unknown_source_raises_key_error():
    with pytest.raises(KeyError):
        shortest_path(GRAPH, "zzz", "a")
    with pytest.raises(KeyError):
        distances(GRAPH, "zzz")


def test_unknown_target_raises_key_error():
    with pytest.raises(KeyError):
        shortest_path(GRAPH, "a", "zzz")


def test_unknown_target_is_an_error_even_when_the_source_is_fine_and_alone():
    with pytest.raises(KeyError):
        shortest_path({"a": {}}, "a", "b")


def test_source_equal_to_an_unknown_target_is_still_unknown():
    with pytest.raises(KeyError):
        shortest_path(GRAPH, "zzz", "zzz")


def test_a_node_that_is_only_a_neighbour_counts_as_known():
    assert shortest_path(GRAPH, "b", "c") == (1, ["b", "c"])
    assert distances(GRAPH, "c") == {"c": 0}


def test_empty_graph_has_no_nodes():
    with pytest.raises(KeyError):
        shortest_path({}, "a", "a")
    with pytest.raises(KeyError):
        distances({}, "a")


def test_both_unknown_still_raises_key_error():
    with pytest.raises(KeyError):
        shortest_path(GRAPH, "no_source", "no_target")
