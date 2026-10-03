import copy

import pytest
from shortestpath import WeightError, distances, shortest_path


def test_calls_leave_the_graph_exactly_as_it_was():
    graph = {"a": {"b": 1, "c": 4}, "b": {"c": 1, "d": 7}, "c": {"d": 2}}
    before = copy.deepcopy(graph)
    shortest_path(graph, "a", "d")
    distances(graph, "a")
    shortest_path(graph, "d", "a")
    shortest_path(graph, "c", "c")
    assert graph == before
    assert list(graph) == ["a", "b", "c"]


def test_no_keys_are_added_for_nodes_that_only_appear_as_neighbours():
    graph = {"a": {"b": 1}}
    shortest_path(graph, "a", "b")
    distances(graph, "a")
    shortest_path(graph, "b", "a")
    distances(graph, "b")
    assert graph == {"a": {"b": 1}}
    assert "b" not in graph


def test_failed_calls_leave_the_graph_alone_too():
    graph = {"a": {"b": -1}, "c": {"d": 1}}
    before = copy.deepcopy(graph)
    with pytest.raises(WeightError):
        shortest_path(graph, "a", "b")
    with pytest.raises(WeightError):
        distances(graph, "c")
    assert graph == before
    graph = {"a": {"b": 1}}
    with pytest.raises(KeyError):
        shortest_path(graph, "a", "zzz")
    with pytest.raises(KeyError):
        distances(graph, "zzz")
    assert graph == {"a": {"b": 1}}


def test_the_result_does_not_alias_the_graph():
    graph = {"a": {"b": 1}}
    result = distances(graph, "a")
    result["zzz"] = 99
    result["a"] = -5
    assert graph == {"a": {"b": 1}}
    assert distances(graph, "a") == {"a": 0, "b": 1}


def test_repeated_calls_give_the_same_answers():
    graph = {"S": {"A": 2, "B": 1}, "A": {"T": 1}, "B": {"T": 2}}
    first = shortest_path(graph, "S", "T")
    assert shortest_path(graph, "S", "T") == first == (3, ["S", "A", "T"])
    path = first[1]
    path.append("junk")
    assert shortest_path(graph, "S", "T") == (3, ["S", "A", "T"])
