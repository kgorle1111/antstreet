import pytest
from toposort import CycleError, layers, toposort


def check_cycle(cycle, graph):
    cycle = list(cycle)
    assert len(cycle) >= 2
    assert cycle[0] == cycle[-1]
    assert len(set(cycle[:-1])) == len(cycle) - 1
    for node, nxt in zip(cycle, cycle[1:], strict=False):
        assert nxt in graph[node]


def test_cycle_error_is_a_value_error():
    assert issubclass(CycleError, ValueError)


def test_self_dependency():
    graph = {"a": ["a"]}
    with pytest.raises(CycleError) as info:
        toposort(graph)
    assert list(info.value.cycle) == ["a", "a"]


def test_two_node_cycle():
    graph = {"a": ["b"], "b": ["a"]}
    with pytest.raises(CycleError) as info:
        toposort(graph)
    check_cycle(info.value.cycle, graph)
    assert set(info.value.cycle) == {"a", "b"}


def test_three_node_cycle_is_directed():
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
    with pytest.raises(CycleError) as info:
        toposort(graph)
    check_cycle(info.value.cycle, graph)
    assert len(info.value.cycle) == 4


def test_cycle_excludes_nodes_that_only_lead_into_or_out_of_it():
    graph = {
        "start": ["x"],
        "x": ["y"],
        "y": ["z"],
        "z": ["x"],
        "tail": ["y"],
        "leaf": [],
    }
    with pytest.raises(CycleError) as info:
        toposort(graph)
    check_cycle(info.value.cycle, graph)
    assert set(info.value.cycle) == {"x", "y", "z"}


def test_cycle_hidden_behind_valid_nodes():
    graph = {"a": [], "b": ["a"], "c": ["b", "d"], "d": ["c"], "e": ["a"]}
    with pytest.raises(CycleError) as info:
        toposort(graph)
    check_cycle(info.value.cycle, graph)


def test_self_dependency_among_valid_nodes():
    with pytest.raises(CycleError) as info:
        toposort({"a": [], "b": ["a", "b"]})
    assert list(info.value.cycle) == ["b", "b"]


def test_layers_raises_too():
    graph = {"a": ["b"], "b": ["a"], "c": []}
    with pytest.raises(CycleError) as info:
        layers(graph)
    check_cycle(info.value.cycle, graph)
    with pytest.raises(CycleError):
        layers({"a": ["a"]})
