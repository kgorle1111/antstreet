from graph import Graph
from metrics import components, degree


def test_empty_graph_has_no_components():
    assert components(Graph()) == []


def test_single_component():
    g = Graph.from_edges([("c", "a"), ("a", "b")])
    assert components(g) == [["a", "b", "c"]]


def test_isolated_nodes_are_components():
    g = Graph()
    g.add_node("x")
    g.add_node("a")
    assert components(g) == [["a"], ["x"]]


def test_largest_first_then_by_first_node():
    g = Graph.from_edges(
        [("p", "q"), ("a", "b"), ("m", "n"), ("x", "y"), ("x", "z"), ("y", "z"), ("b", "c")]
    )
    g.add_node("lone")
    assert components(g) == [
        ["a", "b", "c"],
        ["x", "y", "z"],
        ["m", "n"],
        ["p", "q"],
        ["lone"],
    ]


def test_members_are_sorted_whatever_the_insertion_order():
    g = Graph.from_edges([("z", "m"), ("m", "a"), ("q", "a")])
    assert components(g) == [["a", "m", "q", "z"]]


def test_equal_sizes_order_by_first_member_not_by_insertion():
    g = Graph.from_edges([("y", "z"), ("b", "c"), ("m", "n")])
    assert components(g) == [["b", "c"], ["m", "n"], ["y", "z"]]


def test_components_partition_the_nodes():
    edges = [(str(i), str((i * 7 + 3) % 40)) for i in range(40) if str(i) != str((i * 7 + 3) % 40)]
    g = Graph.from_edges(edges)
    parts = components(g)
    flat = [n for part in parts for n in part]
    assert sorted(flat) == g.nodes()
    assert len(flat) == len(set(flat))
    sizes = [len(p) for p in parts]
    assert sizes == sorted(sizes, reverse=True)
    for part in parts:
        for node in part:
            assert all(other in part for other in g.neighbors(node))


def test_a_bridge_joins_two_components():
    g = Graph.from_edges([("a", "b"), ("c", "d")])
    assert components(g) == [["a", "b"], ["c", "d"]]
    g.add_edge("b", "c")
    assert components(g) == [["a", "b", "c", "d"]]
    assert degree(g, "b") == 2
