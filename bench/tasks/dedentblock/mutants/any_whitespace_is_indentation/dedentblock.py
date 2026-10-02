# Indentation and blankness use str.strip, so non-breaking spaces, form feeds and carriage returns count as whitespace.
import os.path


def _blank(line: str) -> bool:
    return line.strip() == ""


def common_margin(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a str")
    indents = [
        line[: len(line) - len(line.lstrip())] for line in text.split("\n") if not _blank(line)
    ]
    return os.path.commonprefix(indents)


def dedent(text: str) -> str:
    margin = common_margin(text)
    return "\n".join("" if _blank(line) else line[len(margin) :] for line in text.split("\n"))
