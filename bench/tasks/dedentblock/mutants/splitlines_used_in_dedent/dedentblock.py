# dedent splits with str.splitlines, so a trailing newline is lost and \r, \x0b and \x0c end lines.
import os.path


def _blank(line: str) -> bool:
    return line.strip(" \t") == ""


def common_margin(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("text must be a str")
    indents = [
        line[: len(line) - len(line.lstrip(" \t"))] for line in text.split("\n") if not _blank(line)
    ]
    return os.path.commonprefix(indents)


def dedent(text: str) -> str:
    margin = common_margin(text)
    return "\n".join("" if _blank(line) else line[len(margin) :] for line in text.splitlines())
