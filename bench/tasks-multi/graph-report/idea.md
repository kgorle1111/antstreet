Create three Python modules (standard library only) for small undirected graphs: `graph.py` stores a graph, `metrics.py` computes things about one, and `report.py` prints them as text. `metrics.py` and `report.py` only call the public methods of `Graph` named below, they never touch its internals.

`graph.py` provides one class:

    Graph()
    Graph.from_edges(edges: Iterable[tuple[str, str]]) -> Graph        # classmethod
    add_node(node: str) -> None
    add_edge(a: str, b: str) -> None
    has_edge(a: str, b: str) -> bool
    nodes() -> list[str]
    edges() -> list[tuple[str, str]]
    neighbors(node: str) -> list[str]
    len(graph) -> int
    node in graph -> bool

`metrics.py` provides:

    degree(graph, node) -> int
    degree_distribution(graph) -> dict[int, int]
    top_degree(graph, k: int) -> list[tuple[str, int]]
    components(graph) -> list[list[str]]
    shortest_path(graph, a: str, b: str) -> list[str] | None
    density(graph) -> float

`report.py` provides:

    render_report(graph, top: int = 3) -> str
    render_path(graph, a: str, b: str) -> str

Graph:

1. A graph is simple and undirected: no self-loops, at most one edge between two nodes, and an edge between `a` and `b` is the same edge as one between `b` and `a`. Nodes are non-empty `str`s; anything else (including `None`, an int, or `""`) raises `ValueError` from `add_node` and `add_edge`.
2. `add_node(node)` adds a node with no edges; adding an existing node changes nothing. `add_edge(a, b)` adds both nodes if they are missing, then the edge; adding an existing edge (in either direction) changes nothing. `add_edge(a, a)` raises `ValueError`. When `add_edge` raises, the graph is unchanged: neither node is added.
3. `Graph.from_edges(edges)` builds a graph by calling `add_edge` for each pair in order. It builds no isolated nodes.
4. `nodes()` returns a new list of all nodes in ascending order. `edges()` returns a new list of `(a, b)` tuples with `a < b`, one per edge, in ascending order of the tuples. `neighbors(node)` returns a new list of the node's neighbours in ascending order and raises `KeyError` for a node that is not in the graph. `has_edge(a, b)` is `True` when that edge exists and `False` otherwise, also when a node is unknown. `len(graph)` is the number of nodes and `node in graph` says whether the node exists (`None in graph` is `False`).

Metrics (all take a `Graph`; `KeyError` for any node that is not in it):

5. `degree(graph, node)` is the number of neighbours.
6. `degree_distribution(graph)` maps each degree that occurs to the number of nodes having it, with the keys in ascending order (iteration order of the dict). An empty graph gives `{}`.
7. `top_degree(graph, k)` returns up to `k` `(node, degree)` tuples, the nodes of highest degree first, equal degrees in ascending name order. `k` must be an `int` of at least 0 (a `bool` is rejected), otherwise `ValueError`. `k` larger than the number of nodes returns every node.
8. `components(graph)` returns the connected components as lists of nodes. Every component list is in ascending order. The components are ordered by size, largest first, and components of equal size by their first node in ascending order. An isolated node is a component of its own. An empty graph gives `[]`.
9. `shortest_path(graph, a, b)` returns the list of nodes on a path from `a` to `b` with the fewest edges, including both ends, or `None` when there is no path. `shortest_path(graph, a, a)` is `[a]`. When several shortest paths exist, the result is the one that is smallest when the paths are compared as lists of names (the first position where two paths differ decides).
10. `density(graph)` is `2 * edges / (nodes * (nodes - 1))` as a `float`, and `0.0` for a graph with fewer than two nodes.

Report:

11. `render_report(graph, top=3)` returns these lines joined with `"\n"` plus one final `"\n"`; `top` must be an `int` of at least 0 (a `bool` is rejected) or `ValueError` is raised:
    - `Graph report`
    - `Nodes: <number of nodes>`
    - `Edges: <number of edges>`
    - `Density: <density with exactly 2 decimals>`
    - `Components: <number of components>`
    - `Largest component: <size of the largest component, 0 for an empty graph>`
    - `Isolated nodes: <nodes of degree 0 in ascending order separated by ", ", or none>`
    - `Top degrees:` followed by one line `  <node>: <degree>` (two leading spaces) for each entry of `top_degree(graph, top)`
    - `Degree distribution:` followed by one line `  <degree>: <count>` (two leading spaces) per entry of `degree_distribution`, in its order
12. `render_path(graph, a, b)` returns a single line without a newline: `Path <a> -> <b>: <n1> -> <n2> -> ... (<h> hops)` where the names are the nodes of `shortest_path` joined with ` -> ` and `<h>` is the number of edges, written `(1 hop)` when it is exactly 1 and `(0 hops)` for `a == b`; or `Path <a> -> <b>: none` when there is no path. A node that is not in the graph raises `KeyError`.

Example: edges `a-b`, `b-c`, `a-c`, `d-e` and the extra node `f` give

    Graph report
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
