# Folded continuation lines are glued on with no space, so 'one' and 'two' become 'onetwo'.
"""HTTP header block parser: folding, repeated fields, ASCII-only case-insensitive lookup."""

import string

_TOKEN = frozenset(string.ascii_letters + string.digits + "!#$%&'*+-.^_`|~")
# str.lower() would also fold non-ASCII letters (the Kelvin sign), which header names never do
_FOLD = {i: i + 32 for i in range(ord("A"), ord("Z") + 1)}


class Headers:
    def __init__(self, fields: list[tuple[str, str]]) -> None:
        self._fields = list(fields)

    def items(self) -> list[tuple[str, str]]:
        return list(self._fields)

    def get_all(self, name: str) -> list[str]:
        key = name.translate(_FOLD)
        return [value for field, value in self._fields if field.translate(_FOLD) == key]

    def get(self, name: str, default: str | None = None) -> str | None:
        values = self.get_all(name)
        return ", ".join(values) if values else default

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and bool(self.get_all(name))

    def __len__(self) -> int:
        return len(self._fields)


def parse_headers(text: str) -> Headers:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    fields: list[tuple[str, list[str]]] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line == "":
            break
        if line[0] in " \t":
            if not fields:
                raise ValueError("a continuation line has no header above it")
            fields[-1][1].append(line.strip(" \t"))
            continue
        name, colon, value = line.partition(":")
        if not colon or not name or not set(name) <= _TOKEN:
            raise ValueError(f"not a header line: {line!r}")
        fields.append((name, [value.strip(" \t")]))
    return Headers([(name, "".join(p for p in parts if p)) for name, parts in fields])
