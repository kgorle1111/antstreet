# Harvested: a Haiku worker's product (pilot run, firm arm, rep1); fails hidden checks: dependency_only_nodes.
class CycleError(ValueError):
    def __init__(self, message, cycle):
        super().__init__(message)
        self.cycle = cycle


def toposort(dependencies):
    deps = {k: set(v) for k, v in dependencies.items()}

    all_nodes = set(deps.keys())
    for dep_list in deps.values():
        all_nodes.update(dep_list)

    for node in all_nodes:
        if node not in deps:
            deps[node] = set()

    result = []
    remaining = set(all_nodes)

    while remaining:
        available = [node for node in remaining if not (deps[node] & remaining)]

        if not available:
            cycle = _find_cycle(deps, remaining)
            raise CycleError("Cycle detected", cycle)

        available.sort()
        node = available[0]
        result.append(node)
        remaining.remove(node)

    return result


def _find_cycle(deps, nodes):
    visited = set()

    def dfs(node, rec_stack):
        if node in rec_stack:
            idx = rec_stack.index(node)
            return rec_stack[idx:] + [node]

        if node in visited:
            return None

        visited.add(node)
        rec_stack.append(node)

        for neighbor in deps.get(node, set()):
            if neighbor in nodes:
                cycle = dfs(neighbor, rec_stack)
                if cycle:
                    return cycle

        rec_stack.pop()
        return None

    for node in nodes:
        if node not in visited:
            cycle = dfs(node, [])
            if cycle:
                return cycle

    return []


def layers(dependencies):
    topo_order = toposort(dependencies)

    deps = {k: set(v) for k, v in dependencies.items()}

    all_nodes = set(deps.keys())
    for dep_list in deps.values():
        all_nodes.update(dep_list)

    for node in all_nodes:
        if node not in deps:
            deps[node] = set()

    node_layer = {}

    for node in topo_order:
        if deps[node]:
            max_layer = max(node_layer[dep] for dep in deps[node])
            node_layer[node] = max_layer + 1
        else:
            node_layer[node] = 0

    max_layer = max(node_layer.values()) if node_layer else -1
    result = [[] for _ in range(max_layer + 1)]

    for node, layer in node_layer.items():
        result[layer].append(node)

    for layer in result:
        layer.sort()

    return result
