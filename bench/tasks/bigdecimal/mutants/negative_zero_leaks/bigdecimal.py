# A zero result keeps its sign, giving '-0' (for example -5 + 5 or a negative times zero).
"""Digit-list arithmetic. A parsed number is (negative, digits, scale): the value is
+/- (digits read as an integer) / 10**scale, with digits most significant first."""

_DIGITS = frozenset("0123456789")

Parsed = tuple[bool, list[int], int]


def _parse(text: str) -> Parsed:
    if not isinstance(text, str):
        raise ValueError("a decimal must be given as a string")
    negative = text.startswith("-")
    whole, point, frac = text[negative:].partition(".")
    if not whole or (point and not frac) or not set(whole + frac) <= _DIGITS:
        raise ValueError(f"not a decimal number: {text!r}")
    return negative, [ord(c) - ord("0") for c in whole + frac], len(frac)


def _strip(digits: list[int]) -> list[int]:
    start = 0
    while start < len(digits) and digits[start] == 0:
        start += 1
    return digits[start:]


def _align(x: Parsed, y: Parsed) -> tuple[list[int], list[int], int]:
    """Same scale and same length for both digit lists, so they can be combined column-wise."""
    scale = max(x[2], y[2])
    dx = x[1] + [0] * (scale - x[2])
    dy = y[1] + [0] * (scale - y[2])
    width = max(len(dx), len(dy))
    return [0] * (width - len(dx)) + dx, [0] * (width - len(dy)) + dy, scale


def _add_magnitudes(x: list[int], y: list[int]) -> list[int]:
    out, carry = [], 0
    for dx, dy in zip(reversed(x), reversed(y), strict=True):
        carry, digit = divmod(dx + dy + carry, 10)
        out.append(digit)
    if carry:
        out.append(carry)
    return out[::-1]


def _sub_magnitudes(x: list[int], y: list[int]) -> list[int]:
    """x - y for equal-length lists with x >= y."""
    out, borrow = [], 0
    for dx, dy in zip(reversed(x), reversed(y), strict=True):
        digit = dx - dy - borrow
        borrow = 1 if digit < 0 else 0
        out.append(digit + 10 * borrow)
    return out[::-1]


def _mul_magnitudes(x: list[int], y: list[int]) -> list[int]:
    cells = [0] * (len(x) + len(y))  # least significant first
    for i, dx in enumerate(reversed(x)):
        for j, dy in enumerate(reversed(y)):
            cells[i + j] += dx * dy
    carry = 0
    for i, cell in enumerate(cells):
        carry, cells[i] = divmod(cell + carry, 10)
    return cells[::-1]


def _format(negative: bool, digits: list[int], scale: int) -> str:
    digits = _strip(digits)
    if not digits:
        return "-0" if negative else "0"
    digits = [0] * (scale + 1 - len(digits)) + digits
    whole = "".join(map(str, digits[: len(digits) - scale]))
    frac = "".join(map(str, digits[len(digits) - scale :])).rstrip("0")
    return ("-" if negative else "") + whole + ("." + frac if frac else "")


def _signed_sum(x: Parsed, y: Parsed) -> str:
    dx, dy, scale = _align(x, y)
    if x[0] == y[0]:
        return _format(x[0], _add_magnitudes(dx, dy), scale)
    if dx >= dy:  # equal-length digit lists: list order is numeric order
        return _format(x[0], _sub_magnitudes(dx, dy), scale)
    return _format(y[0], _sub_magnitudes(dy, dx), scale)


def add(a: str, b: str) -> str:
    x, y = _parse(a), _parse(b)
    return _signed_sum(x, y)


def subtract(a: str, b: str) -> str:
    x, y = _parse(a), _parse(b)
    return _signed_sum(x, (not y[0], y[1], y[2]))


def multiply(a: str, b: str) -> str:
    x, y = _parse(a), _parse(b)
    return _format(x[0] != y[0], _mul_magnitudes(x[1], y[1]), x[2] + y[2])


def compare(a: str, b: str) -> int:
    difference = subtract(a, b)
    if difference == "0":
        return 0
    return -1 if difference.startswith("-") else 1
