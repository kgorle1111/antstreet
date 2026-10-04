"""Run-length codec with backslash-escaped digits; the decoder is bounded by max_output."""

from itertools import groupby

_DIGITS = "0123456789"  # ASCII only: str.isdigit() would also match digits of other scripts


def _unit(ch: str) -> str:
    return "\\" + ch if ch == "\\" or ch in _DIGITS else ch


def encode(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    return "".join(f"{sum(1 for _ in run)}{_unit(ch)}" for ch, run in groupby(text))


def decode(text: str, max_output: int = 1_000_000) -> str:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    if not isinstance(max_output, int) or isinstance(max_output, bool):
        raise TypeError(f"max_output must be an int, got {type(max_output).__name__}")
    if max_output < 0:
        raise ValueError("max_output must not be negative")
    out: list[str] = []
    total = 0
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and text[j] in _DIGITS:
            j += 1
        digits = text[i:j]
        if not digits or digits[0] == "0":
            raise ValueError(f"expected a count at position {i}")
        if j >= len(text):
            raise ValueError("a count has no character after it")
        ch = text[j]
        j += 1
        if ch == "\\":
            if j >= len(text) or (text[j] != "\\" and text[j] not in _DIGITS):
                raise ValueError("a backslash must be followed by a digit or a backslash")
            ch = text[j]
            j += 1
        count = int(digits)  # int() refuses 4300+ digits with ValueError, which is also right here
        total += count
        if total > max_output:
            raise ValueError(f"output would be longer than {max_output} characters")
        out.append(ch * count)
        i = j
    return "".join(out)
