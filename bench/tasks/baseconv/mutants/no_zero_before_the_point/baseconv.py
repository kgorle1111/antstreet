# A value below one is written without its leading zero, as .5 instead of 0.5.
import re
from fractions import Fraction

_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"
_TEXT = re.compile(r"-?([0-9a-zA-Z]+)(?:\.([0-9a-zA-Z]+))?")


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {value!r}")
    return value


def _base(value: object, name: str) -> int:
    base = _int(value, name)
    if not 2 <= base <= 36:
        raise ValueError(f"{name} must be from 2 to 36, got {base}")
    return base


def parse_number(text: str, base: int) -> Fraction:
    if not isinstance(text, str):
        raise TypeError(f"text must be a str, got {type(text).__name__}")
    base = _base(base, "base")
    match = _TEXT.fullmatch(text)
    if match is None:
        raise ValueError(f"not a number: {text!r}")
    whole, frac = match.groups()
    try:
        value = Fraction(int(whole, base))
        if frac is not None:
            value += Fraction(int(frac, base), base ** len(frac))
    except ValueError:
        raise ValueError(f"a digit is not valid in base {base}: {text!r}") from None
    return -value if text.startswith("-") else value


def _whole_digits(n: int, base: int) -> str:
    out = []
    while n:
        n, d = divmod(n, base)
        out.append(_DIGITS[d])
    return "".join(reversed(out)) or "0"


def convert(text: str, from_base: int, to_base: int, max_frac: int = 10) -> str:
    value = parse_number(text, from_base)
    to_base = _base(to_base, "to_base")
    if _int(max_frac, "max_frac") < 0:
        raise ValueError(f"max_frac must not be negative, got {max_frac}")
    negative, size = value < 0, abs(value)
    whole, rest = divmod(size.numerator, size.denominator)
    remainder = Fraction(rest, size.denominator)
    digits: list[str] = []
    while remainder and len(digits) < max_frac:
        remainder *= to_base
        digit = int(remainder)
        digits.append(_DIGITS[digit])
        remainder -= digit
    fraction = "".join(digits).rstrip("0")
    out = (_whole_digits(whole, to_base) if whole else "") + (f".{fraction}" if fraction else "")
    out = out or "0"
    return f"-{out}" if negative and (whole or fraction) else out
