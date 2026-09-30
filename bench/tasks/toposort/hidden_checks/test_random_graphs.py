import random

import pytest
from toposort import CycleError, layers, toposort


def all_nodes(graph):
    return set(graph) | {d for ds in graph.values() for d in ds}


def oracle_order(graph):
    nodes = all_nodes(graph)
    done = []
    while len(done) < len(nodes):
        ready = [n for n in nodes if n not in done and all(d in done for d in graph.get(n, ()))]
        if not ready:
            return None
        done.append(min(ready))
    return done


def oracle_layers(graph):
    nodes = all_nodes(graph)
    depth = {}
    while len(depth) < len(nodes):
        for n in nodes - set(depth):
            deps = graph.get(n, ())
            if all(d in depth for d in deps):
                depth[n] = 1 + max((depth[d] for d in deps), default=-1)
    return [
        sorted(n for n in nodes if depth[n] == k)
        for k in range(max(depth.values(), default=-1) + 1)
    ]


def random_graph(rng):
    n = rng.randint(1, 8)
    graph = {}
    for node in range(n):
        if rng.random() < 0.8:
            graph[node] = [rng.randrange(n + 2) for _ in range(rng.randint(0, 3))]
    return graph


def test_random_graphs_match_the_oracle():
    rng = random.Random(20240601)
    acyclic = cyclic = 0
    for _ in range(400):
        graph = random_graph(rng)
        expected = oracle_order(graph)
        if expected is None:
            cyclic += 1
            with pytest.raises(CycleError) as info:
                toposort(graph)
            cycle = list(info.value.cycle)
            assert cycle[0] == cycle[-1]
            assert len(set(cycle[:-1])) == len(cycle) - 1
            for a, b in zip(cycle, cycle[1:], strict=False):
                assert b in graph.get(a, ())
            with pytest.raises(CycleError):
                layers(graph)
        else:
            acyclic += 1
            assert toposort(graph) == expected
            assert layers(graph) == oracle_layers(graph)
    assert acyclic > 50
    assert cyclic > 50
