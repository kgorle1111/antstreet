Create a Python module `shortestpath.py` (standard library only) with an exception class and two
functions:

    class WeightError(ValueError): ...
    shortest_path(graph: dict, source, target) -> tuple[number, list] | None
    distances(graph: dict, source) -> dict

`graph` is a directed, weighted graph: it maps each node to a dict `{neighbour: weight}` of the
edges leaving that node. Nodes are hashable and can be compared with `<`. Every key and every
neighbour is a node of the graph; a node that appears only as a neighbour has no outgoing edges.

1. Every weight must be a number greater than 0. A weight that is zero or negative anywhere in the
   graph raises `WeightError`, even on an edge that cannot be reached from `source`. `WeightError`
   is defined in `shortestpath.py` and is a subclass of `ValueError`.
2. A `source` (or, for `shortest_path`, a `target`) that is not a node of the graph raises
   `KeyError`. The weights are checked first: a graph with a bad weight raises `WeightError` even
   when `source` or `target` is also unknown.
3. `shortest_path(graph, source, target)` returns a tuple `(total, path)`: `total` is the sum of the
   weights along the path and `path` is a list of the nodes from `source` to `target`, both
   included. When `source == target` the result is `(0, [source])`. When `target` cannot be reached
   from `source` the result is `None`.
4. Several paths may have the same smallest total. Then the one returned is the path whose node
   list is smallest when two lists are compared the way Python compares lists: look at the first
   position where they differ, and the path with the smaller node there (by `<`) wins. For example
   with edges S to A (weight 2), S to B (1), A to T (1) and B to T (2), both S-A-T and S-B-T cost 3
   and the result is `(3, ["S", "A", "T"])`.
5. `distances(graph, source)` returns a dict with an entry for every node reachable from `source`,
   `source` itself included with distance 0, giving its smallest total weight. Nodes that cannot be
   reached are not in the dict. It applies the weight and `source` checks of rule 1 and 2.
6. Neither function changes `graph`: no keys are added (not even for nodes that appear only as
   neighbours) and no weights are changed.
7. A chain of 50,000 nodes, and a graph of a few thousand nodes with many edges, must be handled in
   a few seconds without hitting Python's recursion limit.
