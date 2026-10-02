# Same as the reference; the bug is in headings.py: Repeated headings all get the plain slug as their anchor instead of numbered suffixes.
def _check_level(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 6:
        raise ValueError("levels must be ints from 1 to 6")


def render_toc(headings, min_level=1, max_level=6):
    _check_level(min_level)
    _check_level(max_level)
    if min_level > max_level:
        raise ValueError("min_level must not be above max_level")
    lines, stack = [], []
    for heading in headings:
        if not min_level <= heading.level <= max_level:
            continue
        while stack and stack[-1] >= heading.level:
            stack.pop()
        text = heading.text.replace("[", "\\[").replace("]", "\\]")
        lines.append(f"{'  ' * len(stack)}- [{text}](#{heading.anchor})")
        stack.append(heading.level)
    return "\n".join(lines) + "\n" if lines else ""
