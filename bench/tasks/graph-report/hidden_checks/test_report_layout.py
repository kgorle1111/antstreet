from graph import Graph
from report import render_report

EXAMPLE = """Graph report
Nodes: 6
Edges: 4
Density: 0.27
Components: 3
Largest component: 3
Isolated nodes: f
Top degrees:
  a: 2
  b: 2
  c: 2
Degree distribution:
  0: 1
  1: 2
  2: 3
"""


def example():
    g = Graph.from_edges([("a", "b"), ("b", "c"), ("a", "c"), ("d", "e")])
    g.add_node("f")
    return g


def test_example_from_the_idea_exactly():
    assert render_report(example()) == EXAMPLE


def test_top_controls_the_number_of_degree_lines():
    text = render_report(example(), top=1)
    assert "Top degrees:\n  a: 2\nDegree distribution:\n" in text
    text = render_report(example(), top=5)
    assert "Top degrees:\n  a: 2\n  b: 2\n  c: 2\n  d: 1\n  e: 1\nDegree distribution:\n" in text
    text = render_report(example(), top=0)
    assert "Top degrees:\nDegree distribution:\n" in text
    assert render_report(example(), top=100).count("\n") == EXAMPLE.count("\n") + 3


def test_report_ends_with_exactly_one_newline():
    text = render_report(example())
    assert text.endswith("  2: 3\n") and not text.endswith("\n\n")


def test_star_graph():
    g = Graph.from_edges([("hub", "x"), ("hub", "y"), ("hub", "z")])
    assert render_report(g, top=2) == (
        "Graph report\n"
        "Nodes: 4\n"
        "Edges: 3\n"
        "Density: 0.50\n"
        "Components: 1\n"
        "Largest component: 4\n"
        "Isolated nodes: none\n"
        "Top degrees:\n"
        "  hub: 3\n"
        "  x: 1\n"
        "Degree distribution:\n"
        "  1: 3\n"
        "  3: 1\n"
    )


def test_several_isolated_nodes_are_joined_and_sorted():
    g = Graph.from_edges([("m", "n")])
    for name in ("z", "b", "k"):
        g.add_node(name)
    lines = render_report(g).splitlines()
    assert "Isolated nodes: b, k, z" in lines
    assert "Components: 4" in lines
    assert "Largest component: 2" in lines


def test_distribution_lines_follow_ascending_degree():
    g = Graph.from_edges([("a", "b"), ("a", "c"), ("a", "d"), ("d", "e")])
    g.add_node("solo")
    lines = render_report(g).splitlines()
    start = lines.index("Degree distribution:")
    assert lines[start + 1 :] == ["  0: 1", "  1: 3", "  2: 1", "  3: 1"]
