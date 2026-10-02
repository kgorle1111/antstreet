# The one-decimal rounding goes through floats and round(), so exact halves round to even or the wrong way.
import re
from fractions import Fraction

_BINARY = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
_DECIMAL = ("B", "KB", "MB", "GB", "TB", "PB")
_FACTORS = {
    **{name: 1024**i for i, name in enumerate(_BINARY)},
    **{name: 1000**i for i, name in enumerate(_DECIMAL)},
    **{letter: 1024 ** (i + 1) for i, letter in enumerate("KMGTP")},
}
_BY_LOWER = {name.lower(): factor for name, factor in _FACTORS.items()}
_SIZE = re.compile(r"([0-9]+(?:\.[0-9]+)?)[ \t]*([A-Za-z]*)")


def _half_up(x: Fraction) -> int:
    return (2 * x.numerator + x.denominator) // (2 * x.denominator)


def parse_size(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    match = _SIZE.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"not a size: {text!r}")
    number, unit = match.groups()
    factor = _BY_LOWER.get(unit.lower()) if unit else 1
    if factor is None:
        raise ValueError(f"unknown unit {unit!r}")
    return _half_up(Fraction(number) * factor)


def format_size(n: int, binary: bool = True) -> str:
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError(f"n must be an int, got {type(n).__name__}")
    if n < 0:
        raise ValueError("n must not be negative")
    step = 1024 if binary else 1000
    names = _BINARY if binary else _DECIMAL
    if n < step:
        return f"{n} B"
    level = 1
    while level < len(names) - 1 and n >= step ** (level + 1):
        level += 1
    tenths = round(10 * n / step**level)
    if tenths >= 10 * step and level < len(names) - 1:
        level += 1
        tenths = round(10 * n / step**level)
    whole, tenth = divmod(tenths, 10)
    return f"{whole}{f'.{tenth}' if tenth else ''} {names[level]}"
