# Harvested: a Haiku worker's product (rerun1 run, firm arm, rep1); fails hidden checks: cycle_error, dependency_only_nodes, random_graphs.
class CycleError(ValueError):
    def __init__(self, cycle):
        self.cycle = cycle
        super().__init__(f"Cycle detected: {cycle}")


def toposort(dependencies):
    # Build set of all nodes
    all_nodes = set(dependencies.keys())
    for deps in dependencies.values():
        for dep in deps:
            all_nodes.add(dep)

    if not all_nodes:
        return []

    # Build in-degree dict and dependency graph
    in_degree = {node: 0 for node in all_nodes}
    graph = {node: [] for node in all_nodes}

    # Process dependencies
    for node, deps_iterable in dependencies.items():
        # Deduplicate dependencies
        unique_deps = set()
        for dep in deps_iterable:
            unique_deps.add(dep)

        # Update graph and in-degree
        for dep in unique_deps:
            in_degree[node] += 1
            graph[dep].append(node)

    # Kahn's algorithm
    result = []
    available = sorted([node for node in all_nodes if in_degree[node] == 0])

    while available:
        node = available.pop(0)
        result.append(node)

        # Process nodes that depend on this node
        next_available = []
        for dependent in graph[node]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                next_available.append(dependent)

        # Merge and re-sort
        available.extend(next_available)
        available.sort()

    # Check for cycles
    if len(result) != len(all_nodes):
        cycle = _find_cycle(dependencies)
        raise CycleError(cycle)

    return result


def layers(dependencies):
    # Build set of all nodes
    all_nodes = set(dependencies.keys())
    for deps in dependencies.values():
        for dep in deps:
            all_nodes.add(dep)

    if not all_nodes:
        return []

    # Compute layer for each node iteratively
    node_layer = {}
    processed = set()

    while len(processed) < len(all_nodes):
        made_progress = False

        for node in all_nodes:
            if node in processed:
                continue

            # Get dependencies
            deps_set = set()
            if node in dependencies:
                for dep in dependencies[node]:
                    deps_set.add(dep)

            # Check if all dependencies are processed
            if all(dep in processed for dep in deps_set):
                # Compute layer
                if deps_set:
                    node_layer[node] = 1 + max(node_layer[dep] for dep in deps_set)
                else:
                    node_layer[node] = 0

                processed.add(node)
                made_progress = True

        if not made_progress:
            # Cycle detected
            cycle = _find_cycle(dependencies)
            raise CycleError(cycle)

    # Group nodes by layer
    max_layer = max(node_layer.values()) if node_layer else -1
    result = []

    for layer_num in range(max_layer + 1):
        layer_nodes = sorted([node for node in all_nodes if node_layer[node] == layer_num])
        result.append(layer_nodes)

    return result


def _find_cycle(dependencies):
    all_nodes = set(dependencies.keys())
    for deps in dependencies.values():
        for dep in deps:
            all_nodes.add(dep)

    # Build dependency graph
    deps_graph = {}
    for node in all_nodes:
        deps_set = set()
        if node in dependencies:
            for dep in dependencies[node]:
                deps_set.add(dep)
        deps_graph[node] = sorted(deps_set)

    # Iterative DFS to find cycle
    state = {}
    parent = {}

    def dfs_iterative(start):
        stack = [start]
        state[start] = 'gray'

        while stack:
            node = stack[-1]

            found_next = False
            for neighbor in deps_graph[node]:
                if neighbor not in state:
                    state[neighbor] = 'gray'
                    parent[neighbor] = node
                    stack.append(neighbor)
                    found_next = True
                    break
                elif state[neighbor] == 'gray':
                    # Found a back edge, construct cycle
                    cycle = []
                    current = node
                    while current != neighbor:
                        cycle.append(current)
                        current = parent[current]
                    cycle.append(neighbor)
                    cycle.append(cycle[0])
                    return cycle

            if not found_next:
                state[node] = 'black'
                stack.pop()

        return None

    for node in sorted(all_nodes):
        if node not in state:
            result = dfs_iterative(node)
            if result:
                return result

    return []
