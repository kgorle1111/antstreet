# An improper fraction is written as n/d (7/2) instead of as a mixed number (3 1/2).
import re
from math import gcd

_FORM = re.compile(
    r"(-?)(?:([0-9]+)[ \t]+([0-9]+)/([0-9]+)|([0-9]+)/([0-9]+)|([0-9]+))"
)


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    return value


def parse_fraction(text: str) -> tuple[int, int]:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    match = _FORM.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"not a fraction: {text!r}")
    minus, whole, mixed_num, mixed_den, num, den, integer = match.groups()
    if integer is not None:
        numerator, denominator = int(integer), 1
    elif num is not None:
        numerator, denominator = int(num), int(den)
    else:
        denominator = int(mixed_den)
        if denominator == 0 or int(mixed_num) >= denominator:
            raise ValueError(f"the fraction in a mixed number must be proper: {text!r}")
        numerator = int(whole) * denominator + int(mixed_num)
    if denominator == 0:
        raise ValueError(f"zero denominator: {text!r}")
    divisor = gcd(numerator, denominator)
    numerator, denominator = numerator // divisor, denominator // divisor
    return (-numerator if minus else numerator), denominator


def format_fraction(numerator: int, denominator: int) -> str:
    _int(numerator, "numerator")
    _int(denominator, "denominator")
    if denominator == 0:
        raise ValueError("zero denominator")
    negative = (numerator < 0) != (denominator < 0)
    divisor = gcd(numerator, denominator)
    top, bottom = abs(numerator) // divisor, abs(denominator) // divisor
    sign = "-" if negative and top else ""
    if bottom == 1:
        return f"{sign}{top}"
    whole, rest = divmod(top, bottom)
    return f"{sign}{top}/{bottom}"


def add(a: str, b: str) -> str:
    (an, ad), (bn, bd) = parse_fraction(a), parse_fraction(b)
    return format_fraction(an * bd + bn * ad, ad * bd)


def divide(a: str, b: str) -> str:
    (an, ad), (bn, bd) = parse_fraction(a), parse_fraction(b)
    if bn == 0:
        raise ValueError("division by zero")
    return format_fraction(an * bd, ad * bn)
