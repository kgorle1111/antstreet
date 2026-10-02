import pytest
from graph import Graph
from metrics import degree, shortest_path


def sample():
    g = Graph.from_edges([("c", "a"), ("a", "b"), ("c", "d"), ("c", "b")])
    g.add_node("lonely")
    return g


def test_neighbors_are_sorted():
    g = sample()
    assert g.neighbors("c") == ["a", "b", "d"]
    assert g.neighbors("a") == ["b", "c"]
    assert g.neighbors("lonely") == []


def test_neighbors_of_unknown_node():
    with pytest.raises(KeyError):
        sample().neighbors("zzz")


def test_has_edge():
    g = sample()
    assert g.has_edge("a", "c") is True
    assert g.has_edge("d", "a") is False
    assert g.has_edge("a", "a") is False
    assert g.has_edge("a", "zzz") is False
    assert g.has_edge("zzz", "yyy") is False
    assert g.has_edge("lonely", "a") is False


def test_queries_return_fresh_lists():
    g = sample()
    for result in (g.nodes(), g.edges(), g.neighbors("c")):
        result.clear()
    assert g.nodes() == ["a", "b", "c", "d", "lonely"]
    assert g.edges() == [("a", "b"), ("a", "c"), ("b", "c"), ("c", "d")]
    assert g.neighbors("c") == ["a", "b", "d"]


def test_queries_do_not_create_nodes():
    g = sample()
    g.has_edge("ghost", "a")
    assert "ghost2" not in g
    with pytest.raises(KeyError):
        g.neighbors("ghost3")
    assert len(g) == 5


def test_metrics_see_later_changes():
    g = sample()
    assert degree(g, "d") == 1
    g.add_edge("d", "lonely")
    assert degree(g, "d") == 2
    assert shortest_path(g, "lonely", "a") == ["lonely", "d", "c", "a"]


def test_names_are_case_sensitive_and_may_contain_odd_characters():
    g = Graph.from_edges([("A", "a"), ("a b", "a-b"), ("é", "e")])
    assert g.nodes() == ["A", "a", "a b", "a-b", "e", "é"]
    assert g.neighbors("A") == ["a"]
    assert g.edges() == [("A", "a"), ("a b", "a-b"), ("e", "é")]


@pytest.mark.parametrize("bad", ["", None, 5, b"a", ("a",)])
def test_bad_node_names(bad):
    g = Graph()
    with pytest.raises(ValueError):
        g.add_node(bad)
    assert len(g) == 0
