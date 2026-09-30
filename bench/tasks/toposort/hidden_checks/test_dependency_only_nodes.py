from toposort import layers, toposort


def test_nodes_listed_only_as_dependencies_are_included():
    assert toposort({"app": ["lib", "util"]}) == ["lib", "util", "app"]


def test_each_node_appears_once():
    graph = {"a": ["x", "y"], "b": ["x"], "c": ["y", "x"]}
    result = toposort(graph)
    assert sorted(result) == ["a", "b", "c", "x", "y"]
    assert len(result) == 5


def test_duplicate_dependencies_mean_one():
    assert toposort({"b": ["a", "a", "a"], "c": ["b", "b"]}) == ["a", "b", "c"]
    assert layers({"b": ["a", "a"]}) == [["a"], ["b"]]


def test_values_may_be_any_iterable():
    graph = {
        "d": (n for n in ["b", "c"]),
        "c": {"a"},
        "b": frozenset(["a"]),
        "a": iter(()),
    }
    assert toposort(graph) == ["a", "b", "c", "d"]


def test_generator_values_work_for_layers_too():
    graph = {"b": (n for n in ["a"]), "c": (n for n in ["a", "b"])}
    assert layers(graph) == [["a"], ["b"], ["c"]]


def test_tuple_nodes():
    graph = {(1, "b"): [(0, "a")], (0, "a"): []}
    assert toposort(graph) == [(0, "a"), (1, "b")]
