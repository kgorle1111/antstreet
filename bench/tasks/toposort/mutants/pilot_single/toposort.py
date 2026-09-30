# Harvested: a Haiku worker's product (pilot run, single arm, rep1); fails hidden checks: cycle_error, dependency_only_nodes, random_graphs.
class CycleError(ValueError):
    def __init__(self, cycle):
        self.cycle = cycle
        super().__init__(f"Cycle detected: {cycle}")


def toposort(dependencies: dict) -> list:
    all_nodes = set(dependencies.keys())
    for deps in dependencies.values():
        for dep in deps:
            all_nodes.add(dep)

    if not all_nodes:
        return []

    # Build in-degree and dependents graph
    in_degree = {node: 0 for node in all_nodes}
    dependents = {node: set() for node in all_nodes}

    for node, deps in dependencies.items():
        seen = set()
        for dep in deps:
            if dep not in seen:
                seen.add(dep)
                in_degree[node] += 1
                dependents[dep].add(node)

    # Kahn's algorithm
    result = []
    queue = [node for node in all_nodes if in_degree[node] == 0]
    queue.sort()

    while queue:
        queue.sort()
        node = queue.pop(0)
        result.append(node)

        for dependent in dependents[node]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Check for cycle
    if len(result) != len(all_nodes):
        cycle = _find_cycle(dependencies, all_nodes)
        raise CycleError(cycle)

    return result


def layers(dependencies: dict) -> list[list]:
    all_nodes = set(dependencies.keys())
    for deps in dependencies.values():
        for dep in deps:
            all_nodes.add(dep)

    if not all_nodes:
        return []

    # Normalize dependencies (remove duplicates)
    node_deps = {}
    for node in all_nodes:
        if node in dependencies:
            seen = set()
            dep_list = []
            for d in dependencies[node]:
                if d not in seen:
                    seen.add(d)
                    dep_list.append(d)
            node_deps[node] = dep_list
        else:
            node_deps[node] = []

    # Compute layers iteratively
    layer = {}
    remaining = set(all_nodes)
    current_layer = 0

    while remaining:
        layer_nodes = []
        for node in remaining:
            if all(d in layer for d in node_deps[node]):
                layer_nodes.append(node)

        if not layer_nodes:
            cycle = _find_cycle(dependencies, all_nodes)
            raise CycleError(cycle)

        layer_nodes.sort()
        for node in layer_nodes:
            layer[node] = current_layer
            remaining.remove(node)

        current_layer += 1

    # Build result
    if not layer:
        return []

    max_layer_num = max(layer.values())
    result = [[] for _ in range(max_layer_num + 1)]

    for node, layer_num in layer.items():
        result[layer_num].append(node)

    for layer_list in result:
        layer_list.sort()

    return result


def _find_cycle(dependencies, all_nodes):
    for start in sorted(all_nodes):
        state = {node: 'white' for node in all_nodes}
        parent = {}
        deps_iter = {}

        stack = [(start, 'enter')]
        state[start] = 'gray'
        parent[start] = None

        while stack:
            node, phase = stack[-1]

            if phase == 'enter':
                deps_list = []
                if node in dependencies:
                    seen = set()
                    for d in dependencies[node]:
                        if d not in seen:
                            seen.add(d)
                            deps_list.append(d)

                deps_iter[node] = iter(deps_list)
                stack[-1] = (node, 'process')

            try:
                dep = next(deps_iter[node])

                if state[dep] == 'white':
                    state[dep] = 'gray'
                    parent[dep] = node
                    stack.append((dep, 'enter'))
                elif state[dep] == 'gray':
                    cycle = [dep]
                    current = node
                    while current != dep:
                        cycle.append(current)
                        current = parent[current]
                    cycle.append(dep)
                    return cycle
            except StopIteration:
                state[node] = 'black'
                stack.pop()

    return None
