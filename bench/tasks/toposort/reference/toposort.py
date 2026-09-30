import heapq


class CycleError(ValueError):
    def __init__(self, cycle: list) -> None:
        super().__init__(f"dependency cycle: {cycle}")
        self.cycle = cycle


def _prepare(dependencies: dict) -> tuple[dict, dict, dict]:
    deps = {node: set(items) for node, items in dependencies.items()}
    for node in [d for items in deps.values() for d in items]:
        deps.setdefault(node, set())
    dependents: dict = {node: [] for node in deps}
    for node, items in deps.items():
        for d in items:
            dependents[d].append(node)
    waiting = {node: len(items) for node, items in deps.items()}
    return deps, dependents, waiting


def _cycle(deps: dict, waiting: dict) -> list:
    stuck = {node for node, count in waiting.items() if count}
    node = min(stuck)
    path: list = []
    seen: dict = {}
    while node not in seen:
        seen[node] = len(path)
        path.append(node)
        node = min(d for d in deps[node] if d in stuck)
    return path[seen[node] :] + [node]


def toposort(dependencies: dict) -> list:
    deps, dependents, waiting = _prepare(dependencies)
    ready = [node for node, count in waiting.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        node = heapq.heappop(ready)
        order.append(node)
        for nxt in dependents[node]:
            waiting[nxt] -= 1
            if waiting[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(order) < len(deps):
        raise CycleError(_cycle(deps, waiting))
    return order


def layers(dependencies: dict) -> list[list]:
    deps, dependents, waiting = _prepare(dependencies)
    current = sorted(node for node, count in waiting.items() if count == 0)
    result = []
    placed = 0
    while current:
        result.append(current)
        placed += len(current)
        following = []
        for node in current:
            for nxt in dependents[node]:
                waiting[nxt] -= 1
                if waiting[nxt] == 0:
                    following.append(nxt)
        current = sorted(following)
    if placed < len(deps):
        raise CycleError(_cycle(deps, waiting))
    return result
