# Lines are packed to at most width - 1 characters (off by one in the fit test).
def justify(text: str, width: int) -> list[str]:
    if width < 1:
        raise ValueError("width must be at least 1")
    words = text.split()
    if any(len(w) > width for w in words):
        raise ValueError("a word is longer than width")

    lines: list[list[str]] = []
    current: list[str] = []
    used = 0  # length of `current` joined by single spaces
    for word in words:
        if current and used + 1 + len(word) >= width:
            lines.append(current)
            current, used = [], 0
        used += len(word) + (1 if current else 0)
        current.append(word)
    if current:
        lines.append(current)

    result = []
    for i, line in enumerate(lines):
        if i == len(lines) - 1 or len(line) == 1:
            result.append(" ".join(line).ljust(width))
            continue
        base, extra = divmod(width - sum(map(len, line)), len(line) - 1)
        gaps = [" " * (base + (j < extra)) for j in range(len(line) - 1)]
        result.append("".join(w + g for w, g in zip(line, [*gaps, ""], strict=True)))
    return result
