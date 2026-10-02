import pytest
from graph import Graph
from report import render_path, render_report


def test_empty_graph_report():
    assert render_report(Graph()) == (
        "Graph report\n"
        "Nodes: 0\n"
        "Edges: 0\n"
        "Density: 0.00\n"
        "Components: 0\n"
        "Largest component: 0\n"
        "Isolated nodes: none\n"
        "Top degrees:\n"
        "Degree distribution:\n"
    )


def test_single_node_report():
    g = Graph()
    g.add_node("only")
    assert render_report(g) == (
        "Graph report\n"
        "Nodes: 1\n"
        "Edges: 0\n"
        "Density: 0.00\n"
        "Components: 1\n"
        "Largest component: 1\n"
        "Isolated nodes: only\n"
        "Top degrees:\n"
        "  only: 0\n"
        "Degree distribution:\n"
        "  0: 1\n"
    )


@pytest.mark.parametrize("top", [-1, 1.5, True, None, "3"])
def test_bad_top(top):
    with pytest.raises(ValueError):
        render_report(Graph.from_edges([("a", "b")]), top=top)


def test_path_line_for_several_hops():
    g = Graph.from_edges([("a", "b"), ("b", "c"), ("c", "d")])
    assert render_path(g, "a", "d") == "Path a -> d: a -> b -> c -> d (3 hops)"
    assert render_path(g, "d", "b") == "Path d -> b: d -> c -> b (2 hops)"


def test_path_line_singular_hop():
    g = Graph.from_edges([("a", "b")])
    assert render_path(g, "a", "b") == "Path a -> b: a -> b (1 hop)"


def test_path_line_to_itself():
    g = Graph()
    g.add_node("x")
    assert render_path(g, "x", "x") == "Path x -> x: x (0 hops)"


def test_path_line_when_unreachable():
    g = Graph.from_edges([("a", "b"), ("c", "d")])
    assert render_path(g, "a", "c") == "Path a -> c: none"


def test_path_line_uses_the_tie_break_and_has_no_newline():
    g = Graph.from_edges([("s", "b"), ("s", "a"), ("b", "t"), ("a", "t")])
    line = render_path(g, "s", "t")
    assert line == "Path s -> t: s -> a -> t (2 hops)"
    assert "\n" not in line


def test_path_line_with_unknown_node():
    g = Graph.from_edges([("a", "b")])
    with pytest.raises(KeyError):
        render_path(g, "a", "nope")
    with pytest.raises(KeyError):
        render_path(g, "nope", "a")
