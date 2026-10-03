from shortestpath import distances, shortest_path


def test_a_chain_of_fifty_thousand_nodes():
    n = 50_000
    graph = {i: {i + 1: 1} for i in range(n - 1)}
    assert shortest_path(graph, 0, n - 1) == (n - 1, list(range(n)))
    assert distances(graph, 0)[n - 1] == n - 1
    assert shortest_path(graph, n - 1, 0) is None


def test_a_chain_with_edges_both_ways():
    n = 50_000
    graph = {i: {} for i in range(n)}
    for i in range(n - 1):
        graph[i][i + 1] = 1
        graph[i + 1][i] = 1
    assert shortest_path(graph, 0, n - 1) == (n - 1, list(range(n)))
    assert shortest_path(graph, n - 1, 0) == (n - 1, list(range(n - 1, -1, -1)))


def test_thousands_of_nodes_with_many_edges():
    n = 3000
    graph = {}
    for i in range(n):
        graph[i] = {j: 2 * (j - i) for j in range(i + 2, min(i + 21, n))}
        if i + 1 < n:
            graph[i][i + 1] = 1
    dist = distances(graph, 0)
    assert dist == {i: i for i in range(n)}
    assert shortest_path(graph, 0, n - 1) == (n - 1, list(range(n)))
    assert shortest_path(graph, 500, 2500) == (2000, list(range(500, 2501)))


def test_many_equal_cost_routes_stay_fast_and_pick_the_smallest():
    layers, width = 40, 30
    source, target = (0, 0), (layers + 1, 0)
    graph = {source: {(1, w): 1 for w in range(width)}}
    for layer in range(1, layers):
        for w in range(width):
            graph[(layer, w)] = {(layer + 1, v): 1 for v in range(width)}
    for w in range(width):
        graph[(layers, w)] = {target: 1}
    total, path = shortest_path(graph, source, target)
    assert total == layers + 1
    assert path == [source, *[(layer, 0) for layer in range(1, layers + 1)], target]
