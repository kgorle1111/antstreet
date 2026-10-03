def wrap(text: str, width: int, first_indent: str = "", rest_indent: str = "") -> list[str]:
    if not all(isinstance(s, str) for s in (text, first_indent, rest_indent)):
        raise ValueError("text and indents must be strings")
    if type(width) is not int or width - len(first_indent) < 1 or width - len(rest_indent) < 1:
        raise ValueError("width must be an int that leaves room after both indents")
    lines: list[str] = []
    open_line = ""  # words of the line being built, without its indent

    def indent() -> str:
        return first_indent if not lines else rest_indent

    for word in text.split():
        if open_line and len(indent()) + len(open_line) + 1 + len(word) <= width:
            open_line += " " + word
            continue
        if open_line:
            lines.append(indent() + open_line)
            open_line = ""
        while width - len(indent()) < len(word):
            room = width - len(indent())
            lines.append(indent() + word[:room])
            word = word[room:]
        open_line = word
    if open_line:
        lines.append(indent() + open_line)
    return lines
