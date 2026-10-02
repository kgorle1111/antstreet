# Blank lines are included when the margin is worked out, so one empty line makes the margin empty.
import os.path


def _blank(line: str) -> bool:
    return line.strip(" \t") == ""


def common_margin(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a str")
    indents = [
        line[: len(line) - len(line.lstrip(" \t"))] for line in text.split("\n")
    ]
    return os.path.commonprefix(indents)


def dedent(text: str) -> str:
    margin = common_margin(text)
    return "\n".join("" if _blank(line) else line[len(margin) :] for line in text.split("\n"))
