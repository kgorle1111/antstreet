# When two shares have equal fractional parts the later one gets the cent instead of the earlier.
from collections.abc import Iterable


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")
    return value


def split_by_ratio(total: int, ratios: Iterable[int]) -> list[int]:
    _int(total, "total")
    weights = [_int(r, "ratio") for r in ratios]
    if not weights:
        raise ValueError("ratios must not be empty")
    if any(w < 0 for w in weights):
        raise ValueError("ratios must not be negative")
    whole = sum(weights)
    if whole == 0:
        raise ValueError("ratios must not add up to zero")
    amount = abs(total)
    shares = [amount * w // whole for w in weights]
    leftover = amount - sum(shares)
    by_remainder = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % whole), -i))
    for i in by_remainder[:leftover]:
        shares[i] += 1
    return shares if total >= 0 else [-s for s in shares]


def split_even(total: int, parts: int) -> list[int]:
    _int(total, "total")
    if _int(parts, "parts") < 1:
        raise ValueError("parts must be at least 1")
    return split_by_ratio(total, [1] * parts)
