Create a Python module `toposort.py` (standard library only; do not import `graphlib`) with an
exception class and two functions:

    class CycleError(ValueError): ...
    toposort(dependencies: dict) -> list
    layers(dependencies: dict) -> list[list]

`dependencies` maps each node to an iterable of the nodes it depends on. Nodes are hashable and can
be compared with `<`.

1. A value may be any iterable (list, tuple, set, generator), may be empty, and may list the same
   dependency more than once (a duplicate means the same as a single mention). Each value is
   consumed at most once.
2. Every node that is a key or appears in any value is a node of the graph. Nodes that appear only
   as dependencies have no dependencies themselves.
3. `toposort` returns a new list that contains every node exactly once, with every node after all
   of its dependencies. An empty dict gives `[]`.
4. The order is deterministic: at each step, output the smallest node (by `<`) among the nodes not
   yet output whose dependencies have all been output already. This is not a layer-by-layer order:
   with `{"a": [], "c": [], "b": ["a"]}` the result is `["a", "b", "c"]`. The result does not
   depend on the insertion order of the dict or on the order inside the dependency iterables.
5. If the graph contains a cycle, including a node that depends on itself, both functions raise
   `CycleError`. `CycleError` is defined in `toposort.py` and is a subclass of `ValueError`.
6. `CycleError.cycle` is a list of nodes forming one cycle: the first and last items are the same
   node, each item depends directly on the item after it, and no other node appears twice. A node
   that depends on itself gives `[node, node]`. Nodes that merely lead into or out of a cycle
   are not in the list. If there are several cycles, any one may be reported.
7. `layers` returns a list of lists. A node with no dependencies is in layer 0; any other node is
   in layer `1 + max(layer of its dependencies)`. Each layer is sorted ascending, no layer is
   empty, and an empty dict gives `[]`.
8. Neither function mutates its argument: no keys are added or removed (including for nodes that
   appear only as dependencies), and concrete containers used as values are left unchanged.
9. A dependency chain of 10,000 nodes must work in both functions without hitting Python's
   recursion limit.
