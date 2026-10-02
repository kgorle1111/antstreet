# Same as the reference; the bug is in metrics.py: components are ordered by first node, not by
# size with the largest first.
from metrics import components, degree, degree_distribution, density, shortest_path, top_degree


def render_report(graph, top=3):
    if isinstance(top, bool) or not isinstance(top, int) or top < 0:
        raise ValueError("top must be an int of at least 0")
    parts = components(graph)
    isolated = [n for n in graph.nodes() if degree(graph, n) == 0]
    lines = [
        "Graph report",
        f"Nodes: {len(graph)}",
        f"Edges: {len(graph.edges())}",
        f"Density: {density(graph):.2f}",
        f"Components: {len(parts)}",
        f"Largest component: {len(parts[0]) if parts else 0}",
        f"Isolated nodes: {', '.join(isolated) or 'none'}",
        "Top degrees:",
    ]
    lines += [f"  {node}: {deg}" for node, deg in top_degree(graph, top)]
    lines.append("Degree distribution:")
    lines += [f"  {deg}: {count}" for deg, count in degree_distribution(graph).items()]
    return "\n".join(lines) + "\n"


def render_path(graph, a, b):
    path = shortest_path(graph, a, b)
    if path is None:
        return f"Path {a} -> {b}: none"
    hops = len(path) - 1
    unit = "hop" if hops == 1 else "hops"
    return f"Path {a} -> {b}: {' -> '.join(path)} ({hops} {unit})"
