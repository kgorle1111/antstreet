from toposort import layers


def test_empty():
    assert layers({}) == []


def test_chain_and_diamond():
    assert layers({"c": ["b"], "b": ["a"], "a": []}) == [["a"], ["b"], ["c"]]
    assert layers({"d": ["b", "c"], "b": ["a"], "c": ["a"]}) == [["a"], ["b", "c"], ["d"]]


def test_node_goes_in_its_earliest_layer_after_all_dependencies():
    graph = {"a": [], "b": ["a"], "c": ["a", "b"], "d": []}
    assert layers(graph) == [["a", "d"], ["b"], ["c"]]


def test_longest_path_decides_the_layer():
    graph = {"a": [], "b": ["a"], "c": ["b"], "d": ["a", "c"], "e": ["a"]}
    assert layers(graph) == [["a"], ["b", "e"], ["c"], ["d"]]


def test_layers_are_sorted():
    graph = {"z": [], "m": [], "b": [], "q": ["z", "m", "b"], "c": ["b"]}
    assert layers(graph) == [["b", "m", "z"], ["c", "q"]]
    assert layers({3: [], 1: [], 2: [], 10: [1]}) == [[1, 2, 3], [10]]


def test_dependency_only_nodes_are_in_layer_zero():
    assert layers({"app": ["lib", "core"]}) == [["core", "lib"], ["app"]]


def test_returns_lists_of_lists():
    result = layers({"b": ["a"]})
    assert isinstance(result, list)
    assert all(isinstance(layer, list) for layer in result)
