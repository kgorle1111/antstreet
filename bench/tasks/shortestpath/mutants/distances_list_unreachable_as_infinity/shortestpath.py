# distances includes every node of the graph, giving unreachable ones an infinite distance, instead of leaving them out.
import heapq
from typing import Any


class WeightError(ValueError):
    pass


def _check_weights(graph: dict) -> None:
    for node, edges in graph.items():
        for neighbour, weight in edges.items():
            if not weight > 0:
                raise WeightError(f"edge {node!r} -> {neighbour!r} has weight {weight!r}")


def _all_nodes(graph: dict) -> set:
    nodes = set(graph)
    for edges in graph.values():
        nodes.update(edges)
    return nodes


def _dijkstra(edges: dict, start: Any) -> dict:
    """Smallest distance from `start` to every node it can reach; `edges` may lack some nodes."""
    dist = {start: 0}
    done: set = set()
    heap = [(0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        for nxt, weight in edges.get(node, {}).items():
            candidate = d + weight
            if nxt not in dist or candidate < dist[nxt]:
                dist[nxt] = candidate
                heapq.heappush(heap, (candidate, nxt))
    return dist


def shortest_path(graph: dict, source: Any, target: Any) -> tuple[Any, list] | None:
    _check_weights(graph)
    nodes = _all_nodes(graph)
    if source not in nodes:
        raise KeyError(source)
    if target not in nodes:
        raise KeyError(target)
    # Distances *to* the target, from a search on the reversed graph. Walking forward and always
    # taking the smallest neighbour that stays on a shortest route gives the smallest node list;
    # weights are positive, so every step gets strictly closer and the walk cannot loop.
    reverse: dict = {}
    for node, edges in graph.items():
        for neighbour, weight in edges.items():
            reverse.setdefault(neighbour, {})[node] = weight
    remaining = _dijkstra(reverse, target)
    if source not in remaining:
        return None
    path = [source]
    node = source
    while node != target:
        node = min(
            nxt
            for nxt, weight in graph[node].items()
            if nxt in remaining and weight + remaining[nxt] == remaining[node]
        )
        path.append(node)
    return remaining[source], path


def distances(graph: dict, source: Any) -> dict:
    _check_weights(graph)
    if source not in _all_nodes(graph):
        raise KeyError(source)
    dist = _dijkstra(graph, source)
    return {node: dist.get(node, float("inf")) for node in _all_nodes(graph)}
