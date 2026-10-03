# Same as the reference; the bug is in metrics.py: density uses edges / (nodes * (nodes - 1)), the
# directed-graph formula.
def _check(node):
    if not isinstance(node, str) or not node:
        raise ValueError("a node must be a non-empty str")


class Graph:
    def __init__(self):
        self._adjacent = {}

    @classmethod
    def from_edges(cls, edges):
        graph = cls()
        for a, b in edges:
            graph.add_edge(a, b)
        return graph

    def add_node(self, node):
        _check(node)
        self._adjacent.setdefault(node, set())

    def add_edge(self, a, b):
        _check(a)
        _check(b)
        if a == b:
            raise ValueError("self-loops are not allowed")
        self._adjacent.setdefault(a, set()).add(b)
        self._adjacent.setdefault(b, set()).add(a)

    def has_edge(self, a, b):
        return b in self._adjacent.get(a, ())

    def nodes(self):
        return sorted(self._adjacent)

    def edges(self):
        return sorted((a, b) for a, others in self._adjacent.items() for b in others if a < b)

    def neighbors(self, node):
        return sorted(self._adjacent[node])

    def __len__(self):
        return len(self._adjacent)

    def __contains__(self, node):
        return node in self._adjacent
