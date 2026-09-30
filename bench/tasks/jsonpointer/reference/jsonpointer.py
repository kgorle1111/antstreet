import copy
import re
from typing import Any

_TOKEN = re.compile(r"(?:[^~]|~[01])*")


def _parse(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"pointer must be empty or start with '/': {pointer!r}")
    raw = pointer[1:].split("/")
    if not all(_TOKEN.fullmatch(token) for token in raw):
        raise ValueError(f"invalid '~' escape in pointer: {pointer!r}")
    return [token.replace("~1", "/").replace("~0", "~") for token in raw]


def _is_index(token: str) -> bool:
    return token.isascii() and token.isdigit() and (token == "0" or token[0] != "0")


def _child(node: Any, token: str) -> Any:
    if isinstance(node, dict):
        return node[token]
    if isinstance(node, list) and _is_index(token) and int(token) < len(node):
        return node[int(token)]
    raise KeyError(token)


def resolve(document: Any, pointer: str) -> Any:
    node = document
    for token in _parse(pointer):
        node = _child(node, token)
    return node


def set_value(document: Any, pointer: str, value: Any) -> Any:
    tokens = _parse(pointer)
    if not tokens:
        return value
    result = copy.deepcopy(document)
    parent = result
    for token in tokens[:-1]:
        parent = _child(parent, token)
    last = tokens[-1]
    if isinstance(parent, dict):
        parent[last] = value
    elif isinstance(parent, list) and last == "-":
        parent.append(value)
    elif isinstance(parent, list):
        _child(parent, last)
        parent[int(last)] = value
    else:
        raise KeyError(last)
    return result
