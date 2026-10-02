import pytest
from graph import Graph
from metrics import shortest_path


def test_direct_and_trivial_paths():
    g = Graph.from_edges([("a", "b")])
    assert shortest_path(g, "a", "b") == ["a", "b"]
    assert shortest_path(g, "b", "a") == ["b", "a"]
    assert shortest_path(g, "a", "a") == ["a"]


def test_isolated_node_path_to_itself():
    g = Graph()
    g.add_node("x")
    assert shortest_path(g, "x", "x") == ["x"]


def test_fewest_edges_wins_over_alphabetical_order():
    g = Graph.from_edges([("a", "b"), ("b", "c"), ("c", "z"), ("a", "z")])
    assert shortest_path(g, "a", "z") == ["a", "z"]


def test_ties_are_broken_by_smallest_name_list():
    g = Graph.from_edges([("s", "b"), ("s", "a"), ("b", "t"), ("a", "t")])
    assert shortest_path(g, "s", "t") == ["s", "a", "t"]


def test_ties_are_broken_the_same_way_whatever_the_insertion_order():
    edges = [("s", "c"), ("s", "b"), ("s", "a"), ("c", "t"), ("b", "t"), ("a", "t")]
    for ordering in (edges, edges[::-1]):
        assert shortest_path(Graph.from_edges(ordering), "s", "t") == ["s", "a", "t"]


def test_tie_break_applies_at_every_step():
    # two layers of choices: s -> {a, b} -> {c, d} -> t, every middle node linked both ways
    g = Graph.from_edges(
        [
            ("s", "b"),
            ("s", "a"),
            ("a", "d"),
            ("a", "c"),
            ("b", "c"),
            ("b", "d"),
            ("c", "t"),
            ("d", "t"),
        ]
    )
    assert shortest_path(g, "s", "t") == ["s", "a", "c", "t"]


def test_a_smaller_first_step_is_not_taken_when_it_leads_to_a_longer_path():
    g = Graph.from_edges([("s", "a"), ("a", "c"), ("c", "t"), ("s", "b"), ("b", "t")])
    assert shortest_path(g, "s", "t") == ["s", "b", "t"]
    g.add_edge("s", "t")
    assert shortest_path(g, "s", "t") == ["s", "t"]


def test_no_path_between_components():
    g = Graph.from_edges([("a", "b"), ("c", "d")])
    assert shortest_path(g, "a", "d") is None
    g.add_node("e")
    assert shortest_path(g, "a", "e") is None
    assert shortest_path(g, "e", "a") is None


def test_unknown_nodes_raise_key_error():
    g = Graph.from_edges([("a", "b")])
    for a, b in [("a", "zz"), ("zz", "a"), ("zz", "zz"), ("zz", "yy")]:
        with pytest.raises(KeyError):
            shortest_path(g, a, b)


def test_long_path_graph():
    names = [f"n{i:03d}" for i in range(300)]
    g = Graph.from_edges(zip(names, names[1:], strict=False))
    assert shortest_path(g, names[0], names[-1]) == names
    assert shortest_path(g, names[-1], names[0]) == names[::-1]
