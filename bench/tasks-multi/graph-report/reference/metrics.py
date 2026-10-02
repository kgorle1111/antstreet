from collections import Counter, deque


def degree(graph, node):
    return len(graph.neighbors(node))


def degree_distribution(graph):
    counts = Counter(degree(graph, node) for node in graph.nodes())
    return dict(sorted(counts.items()))


def top_degree(graph, k):
    if isinstance(k, bool) or not isinstance(k, int) or k < 0:
        raise ValueError("k must be an int of at least 0")
    ranked = sorted(((n, degree(graph, n)) for n in graph.nodes()), key=lambda p: (-p[1], p[0]))
    return ranked[:k]


def components(graph):
    seen = set()
    found = []
    for start in graph.nodes():
        if start in seen:
            continue
        seen.add(start)
        stack, members = [start], []
        while stack:
            node = stack.pop()
            members.append(node)
            for other in graph.neighbors(node):
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        found.append(sorted(members))
    return sorted(found, key=lambda c: (-len(c), c[0]))


def shortest_path(graph, a, b):
    for node in (a, b):
        if node not in graph:
            raise KeyError(node)
    # Neighbours are visited in ascending order, so the first path found to a node is the
    # smallest of its shortest paths.
    parent = {a: None}
    queue = deque([a])
    while queue:
        node = queue.popleft()
        if node == b:
            break
        for other in graph.neighbors(node):
            if other not in parent:
                parent[other] = node
                queue.append(other)
    if b not in parent:
        return None
    path = []
    while b is not None:
        path.append(b)
        b = parent[b]
    return path[::-1]


def density(graph):
    n = len(graph)
    if n < 2:
        return 0.0
    return 2 * len(graph.edges()) / (n * (n - 1))
