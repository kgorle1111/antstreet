# To_roman accepts True as 1 because bool is a subclass of int.
_SYMBOLS = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)


def to_roman(n: int) -> str:
    if not isinstance(n, int) or not 1 <= n <= 3999:
        raise ValueError(f"{n!r} is not an integer from 1 to 3999")
    parts = []
    for value, symbol in _SYMBOLS:
        count, n = divmod(n, value)
        parts.append(symbol * count)
    return "".join(parts)


def from_roman(s: str) -> int:
    if not isinstance(s, str):
        raise ValueError(f"{s!r} is not a string")
    total = 0
    pos = 0
    for value, symbol in _SYMBOLS:
        while s.startswith(symbol, pos):
            total += value
            pos += len(symbol)
    # Greedy parsing accepts every sloppy spelling; the round trip keeps only canonical ones.
    # to_roman also rejects totals outside 1..3999 (empty string, MMMM).
    if to_roman(total) != s:
        raise ValueError(f"{s!r} is not a canonical Roman numeral")
    return total
