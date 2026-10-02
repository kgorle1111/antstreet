import pytest
from graph import Graph
from metrics import components, degree


def test_empty_graph():
    g = Graph()
    assert len(g) == 0
    assert g.nodes() == []
    assert g.edges() == []
    assert "a" not in g
    assert None not in g


def test_add_node_and_edge():
    g = Graph()
    g.add_node("a")
    g.add_edge("b", "c")
    assert g.nodes() == ["a", "b", "c"]
    assert g.edges() == [("b", "c")]
    assert len(g) == 3
    assert "a" in g and "c" in g and "z" not in g


def test_edge_is_undirected_and_not_duplicated():
    g = Graph()
    g.add_edge("b", "a")
    g.add_edge("a", "b")
    g.add_edge("b", "a")
    assert g.edges() == [("a", "b")]
    assert g.has_edge("a", "b") and g.has_edge("b", "a")
    assert degree(g, "a") == degree(g, "b") == 1


def test_edges_are_sorted_tuples_with_smaller_name_first():
    g = Graph.from_edges([("z", "a"), ("m", "b"), ("b", "a"), ("c", "z")])
    assert g.edges() == [("a", "b"), ("a", "z"), ("b", "m"), ("c", "z")]


def test_adding_a_node_twice_keeps_its_edges():
    g = Graph.from_edges([("a", "b")])
    g.add_node("a")
    assert g.neighbors("a") == ["b"]
    assert len(g) == 2


def test_from_edges_builds_no_isolated_nodes_and_accepts_any_iterable():
    g = Graph.from_edges(iter([("a", "b"), ("b", "c")]))
    assert g.nodes() == ["a", "b", "c"]
    assert Graph.from_edges([]).nodes() == []
    assert Graph.from_edges((("x", "y"),)).edges() == [("x", "y")]
    assert isinstance(g, Graph)


def test_self_loop_is_rejected_and_adds_nothing():
    g = Graph()
    with pytest.raises(ValueError):
        g.add_edge("a", "a")
    assert len(g) == 0
    assert "a" not in g


def test_a_failed_add_edge_leaves_the_graph_unchanged():
    g = Graph.from_edges([("a", "b")])
    for bad in [("c", ""), ("", "c"), ("c", None), (None, "c"), ("c", 5), ("c", "c")]:
        with pytest.raises(ValueError):
            g.add_edge(*bad)
    assert g.nodes() == ["a", "b"]
    assert g.edges() == [("a", "b")]


def test_graphs_do_not_share_state():
    one, two = Graph(), Graph()
    one.add_edge("a", "b")
    assert len(two) == 0
    assert components(two) == []
