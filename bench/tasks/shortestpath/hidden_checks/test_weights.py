import pytest
from shortestpath import WeightError, distances, shortest_path


def test_weight_error_is_a_value_error_defined_in_the_module():
    assert issubclass(WeightError, ValueError)


@pytest.mark.parametrize("weight", [0, 0.0, -1, -0.5, -100])
def test_zero_and_negative_weights_on_the_way_raise(weight):
    graph = {"a": {"b": 1}, "b": {"c": weight}}
    with pytest.raises(WeightError):
        shortest_path(graph, "a", "c")
    with pytest.raises(WeightError):
        distances(graph, "a")


def test_a_zero_weight_edge_is_rejected_even_on_a_tiny_graph():
    with pytest.raises(WeightError):
        shortest_path({"a": {"b": 0}}, "a", "b")
    with pytest.raises(WeightError):
        distances({"a": {"b": 0}}, "a")


def test_a_bad_weight_off_the_search_path_is_still_rejected():
    graph = {"a": {"b": 1}, "x": {"y": -3}}
    with pytest.raises(WeightError):
        shortest_path(graph, "a", "b")
    with pytest.raises(WeightError):
        distances(graph, "a")


def test_a_bad_weight_on_an_edge_that_cannot_be_reached_from_the_source():
    graph = {"a": {"b": 1}, "b": {}, "c": {"a": -1}}
    with pytest.raises(WeightError):
        shortest_path(graph, "a", "b")
    with pytest.raises(WeightError):
        distances(graph, "a")


def test_a_bad_weight_on_an_edge_that_cannot_reach_the_target():
    graph = {"a": {"b": 1, "dead": 2}, "dead": {"more": -2}}
    with pytest.raises(WeightError):
        shortest_path(graph, "a", "b")


def test_a_bad_weight_is_rejected_even_when_source_equals_target():
    with pytest.raises(WeightError):
        shortest_path({"a": {"b": -1}}, "a", "a")


def test_weights_are_checked_before_the_nodes():
    graph = {"a": {"b": -1}}
    with pytest.raises(WeightError):
        shortest_path(graph, "nope", "b")
    with pytest.raises(WeightError):
        shortest_path(graph, "a", "nope")
    with pytest.raises(WeightError):
        distances(graph, "nope")


def test_tiny_positive_weights_are_fine():
    graph = {"a": {"b": 1e-9}, "b": {"c": 1}}
    total, path = shortest_path(graph, "a", "c")
    assert path == ["a", "b", "c"]
    assert total == 1e-9 + 1
    assert distances(graph, "a")["b"] == 1e-9
