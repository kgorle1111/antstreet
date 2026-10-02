import itertools

import pytest
from graph import Graph
from metrics import density
from report import render_report


def test_small_graphs_have_density_zero():
    assert density(Graph()) == 0.0
    g = Graph()
    g.add_node("a")
    assert density(g) == 0.0
    assert isinstance(density(g), float)


def test_two_nodes():
    g = Graph()
    g.add_node("a")
    g.add_node("b")
    assert density(g) == 0.0
    g.add_edge("a", "b")
    assert density(g) == 1.0


def test_path_of_three():
    g = Graph.from_edges([("a", "b"), ("b", "c")])
    assert density(g) == pytest.approx(2 / 3)


def test_complete_graph_is_one():
    names = list("abcde")
    g = Graph.from_edges(itertools.combinations(names, 2))
    assert density(g) == pytest.approx(1.0)


def test_example_density():
    g = Graph.from_edges([("a", "b"), ("b", "c"), ("a", "c"), ("d", "e")])
    g.add_node("f")
    assert density(g) == pytest.approx(8 / 30)


def test_adding_a_duplicate_edge_does_not_change_density():
    g = Graph.from_edges([("a", "b"), ("b", "c")])
    before = density(g)
    g.add_edge("c", "b")
    assert density(g) == before


def test_report_prints_density_with_two_decimals():
    g = Graph.from_edges([("a", "b"), ("b", "c")])
    assert "Density: 0.67\n" in render_report(g)
    g = Graph.from_edges([("a", "b")])
    assert "Density: 1.00\n" in render_report(g)
    g.add_node("c")
    assert "Density: 0.33\n" in render_report(g)
    assert "Density: 0.00\n" in render_report(Graph())
