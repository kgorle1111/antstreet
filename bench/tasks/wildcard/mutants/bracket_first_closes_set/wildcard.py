# A ] directly after [ closes the set instead of being a member, so []] is an error.
from collections.abc import Iterable

# A compiled pattern is a list of tokens. STAR stands for `*`; every other token matches exactly
# one character and is (negated, ranges). Literals and `?` are expressed as sets too.
STAR = None
_Set = tuple[bool, tuple[tuple[str, str], ...]]
_ANY: _Set = (True, ())


def _set_char(pattern: str, i: int) -> tuple[str, int]:
    if pattern[i] == "\\":
        if i + 1 >= len(pattern):
            raise ValueError("pattern ends with a lone backslash")
        return pattern[i + 1], i + 2
    return pattern[i], i + 1


def _parse_set(pattern: str, i: int) -> tuple[_Set, int]:
    """`i` is the index just after the opening `[`."""
    negated = pattern[i : i + 1] == "!"
    if negated:
        i += 1
    ranges: list[tuple[str, str]] = []
    first = True
    while True:
        if i >= len(pattern):
            raise ValueError("unclosed '['")
        if pattern[i] == "]":
            return (negated, tuple(ranges)), i + 1
        first = False
        low, i = _set_char(pattern, i)
        if i + 1 < len(pattern) and pattern[i] == "-" and pattern[i + 1] != "]":
            high, i = _set_char(pattern, i + 1)
            ranges.append((low, high))
        else:
            ranges.append((low, low))


def _compile(pattern: str) -> list[_Set | None]:
    tokens: list[_Set | None] = []
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "*":
            if not tokens or tokens[-1] is not STAR:
                tokens.append(STAR)
            i += 1
        elif char == "?":
            tokens.append(_ANY)
            i += 1
        elif char == "[":
            token, i = _parse_set(pattern, i + 1)
            tokens.append(token)
        else:
            literal, i = _set_char(pattern, i)
            tokens.append((False, ((literal, literal),)))
    return tokens


def _hits(token: _Set, char: str) -> bool:
    negated, ranges = token
    return any(low <= char <= high for low, high in ranges) != negated


def _run(tokens: list[_Set | None], text: str) -> bool:
    # Greedy with a single backtrack point: a later `*` never needs to revisit an earlier one,
    # so the worst case is O(len(text) * len(tokens)).
    t = p = 0
    star = -1
    mark = 0
    while t < len(text):
        token = tokens[p] if p < len(tokens) else None
        if token is not STAR and _hits(token, text[t]):
            p += 1
            t += 1
        elif token is STAR and p < len(tokens):
            star, mark = p, t
            p += 1
        elif star >= 0:
            mark += 1
            t = mark
            p = star + 1
        else:
            return False
    return all(token is STAR for token in tokens[p:])


def match(pattern: str, text: str) -> bool:
    return _run(_compile(pattern), text)


def filter_names(pattern: str, names: Iterable[str]) -> list[str]:
    tokens = _compile(pattern)
    return [name for name in names if _run(tokens, name)]
