import re
from dataclasses import dataclass


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Command:
    name: str
    item_id: int | None = None
    text: str | None = None
    priority: int | None = None
    tags: tuple[str, ...] = ()
    status: str | None = None


def _is_tag(word):
    return word.startswith("#") and len(word) > 1


def _parse_add(args):
    text, tags, priority = [], [], None
    for word in args:
        if _is_tag(word):
            tags.append(word[1:])
        elif re.fullmatch(r"![0-9]+", word):
            if priority is not None:
                raise ParseError("priority given twice")
            priority = int(word[1:])
            if priority not in (1, 2, 3):
                raise ParseError(f"priority must be 1, 2 or 3, got {word}")
        else:
            text.append(word)
    if not text:
        raise ParseError("add needs some text")
    return Command("add", text=" ".join(text), priority=priority, tags=tuple(tags))


def _parse_id(name, args):
    if len(args) != 1 or not re.fullmatch(r"[0-9]+", args[0]) or int(args[0]) < 1:
        raise ParseError(f"{name} needs one item number")
    return Command(name, item_id=int(args[0]))


def _parse_list(args):
    status, tag = None, None
    for word in args:
        if word.lower() in ("open", "done", "all"):
            if status is not None:
                raise ParseError("status given twice")
            status = word.lower()
        elif _is_tag(word):
            if tag is not None:
                raise ParseError("tag given twice")
            tag = word[1:]
        else:
            raise ParseError(f"unexpected word {word!r}")
    return Command("list", status=status or "open", tags=() if tag is None else (tag,))


def parse_command(line):
    if not isinstance(line, str):
        raise ParseError("a command must be a str")
    words = line.split()
    if not words:
        raise ParseError("empty command")
    name, args = words[0].lower(), words[1:]
    if name == "add":
        return _parse_add(args)
    if name in ("done", "rm"):
        return _parse_id(name, args)
    if name == "list":
        return _parse_list(args)
    raise ParseError(f"unknown command {words[0]!r}")
