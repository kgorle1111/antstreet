import random

from shortestpath import distances, shortest_path


def brute_force(graph, source, target):
    """Every simple path by depth-first search; cheapest total, then smallest node list."""
    best = None

    def walk(node, path, total):
        nonlocal best
        if node == target:
            candidate = (total, list(path))
            if best is None or candidate < best:
                best = candidate
            return
        for nxt, weight in graph.get(node, {}).items():
            if nxt not in path:
                path.append(nxt)
                walk(nxt, path, total + weight)
                path.pop()

    walk(source, [source], 0)
    return best


def random_graph(rng):
    n = rng.randint(2, 7)
    nodes = list(range(n))
    graph = {}
    for u in nodes:
        if rng.random() < 0.85:
            graph[u] = {v: rng.randint(1, 3) for v in nodes if v != u and rng.random() < 0.4}
    return nodes, graph


def test_random_small_graphs_match_brute_force_including_ties():
    rng = random.Random(2026)
    reachable = 0
    for _ in range(400):
        nodes, graph = random_graph(rng)
        known = set(graph) | {v for edges in graph.values() for v in edges}
        if not known:
            continue
        source, target = rng.choice(sorted(known)), rng.choice(sorted(known))
        expected = brute_force(graph, source, target)
        got = shortest_path(graph, source, target)
        if expected is None:
            assert got is None
        else:
            assert got == (expected[0], expected[1])
            reachable += 1
    assert reachable > 100


def test_random_graphs_distances_match_brute_force():
    rng = random.Random(77)
    for _ in range(200):
        nodes, graph = random_graph(rng)
        known = sorted(set(graph) | {v for edges in graph.values() for v in edges})
        if not known:
            continue
        source = rng.choice(known)
        got = distances(graph, source)
        expected = {}
        for node in known:
            best = brute_force(graph, source, node)
            if best is not None:
                expected[node] = best[0]
        assert got == expected
