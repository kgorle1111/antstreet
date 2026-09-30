from toposort import layers, toposort

N = 10_000


def test_long_chain_toposort():
    graph = {i: [i - 1] for i in range(1, N)}
    graph[0] = []
    assert toposort(graph) == list(range(N))


def test_long_chain_reversed_keys():
    graph = {i: [i + 1] for i in range(N - 1)}
    assert toposort(graph) == list(range(N - 1, -1, -1))


def test_long_chain_layers():
    graph = {i: [i - 1] for i in range(1, N)}
    result = layers(graph)
    assert len(result) == N
    assert result[0] == [0]
    assert result[-1] == [N - 1]


def test_wide_graph():
    graph = {i: [-1] for i in range(5000)}
    assert toposort(graph) == list(range(-1, 5000))
    assert layers(graph) == [[-1], list(range(5000))]
