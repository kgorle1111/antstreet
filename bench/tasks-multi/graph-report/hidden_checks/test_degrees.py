import pytest
from graph import Graph
from metrics import degree, degree_distribution, top_degree

STAR = [("hub", "a"), ("hub", "b"), ("hub", "c"), ("hub", "d")]


def test_degree():
    g = Graph.from_edges(STAR)
    g.add_node("alone")
    assert degree(g, "hub") == 4
    assert degree(g, "a") == 1
    assert degree(g, "alone") == 0
    assert isinstance(degree(g, "hub"), int)


def test_degree_of_unknown_node():
    with pytest.raises(KeyError):
        degree(Graph(), "x")
    with pytest.raises(KeyError):
        degree(Graph.from_edges(STAR), "nope")


def test_degree_distribution():
    g = Graph.from_edges(STAR + [("a", "b")])
    g.add_node("alone")
    # hub 4, a 2, b 2, c 1, d 1, alone 0
    dist = degree_distribution(g)
    assert dist == {0: 1, 1: 2, 2: 2, 4: 1}
    assert list(dist) == [0, 1, 2, 4]


def test_degree_distribution_keys_come_out_ascending():
    g = Graph.from_edges([("x", "y"), ("x", "z"), ("x", "w"), ("w", "v")])
    assert list(degree_distribution(g)) == [1, 2, 3]


def test_degree_distribution_of_an_empty_graph():
    assert degree_distribution(Graph()) == {}


def test_top_degree_orders_by_degree_then_name():
    g = Graph.from_edges(STAR + [("a", "b"), ("c", "d")])
    # hub 4, a 2, b 2, c 2, d 2
    assert top_degree(g, 3) == [("hub", 4), ("a", 2), ("b", 2)]
    assert top_degree(g, 1) == [("hub", 4)]
    assert top_degree(g, 5) == [("hub", 4), ("a", 2), ("b", 2), ("c", 2), ("d", 2)]


def test_top_degree_k_edge_cases():
    g = Graph.from_edges(STAR)
    assert top_degree(g, 0) == []
    assert len(top_degree(g, 99)) == 5
    assert top_degree(Graph(), 3) == []


def test_top_degree_includes_isolated_nodes_last():
    g = Graph.from_edges([("a", "b")])
    g.add_node("0lone")
    assert top_degree(g, 3) == [("a", 1), ("b", 1), ("0lone", 0)]


@pytest.mark.parametrize("k", [-1, 1.0, 2.5, True, None, "3"])
def test_top_degree_rejects_bad_k(k):
    with pytest.raises(ValueError):
        top_degree(Graph.from_edges(STAR), k)
