_DIGITS = "0123456789"


def _digits(text: str) -> list[int] | None:
    """The digits of `text` with spaces and hyphens removed, or None if anything else is left."""
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    bare = text.replace(" ", "").replace("-", "")
    if any(ch not in _DIGITS for ch in bare):
        return None
    return [int(ch) for ch in bare]


def _checksum(digits: list[int]) -> int:
    total = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total


def is_valid(text: str) -> bool:
    digits = _digits(text)
    return digits is not None and len(digits) >= 2 and _checksum(digits) % 10 == 0


def check_digit(payload: str) -> int:
    digits = _digits(payload)
    if not digits:
        raise ValueError("payload must hold at least one digit and nothing but digits")
    # The appended digit sits in position 0 and is not doubled; the payload shifts left by one.
    return (10 - _checksum([*digits, 0]) % 10) % 10


def with_check_digit(payload: str) -> str:
    digits = _digits(payload)
    if not digits:
        raise ValueError("payload must hold at least one digit and nothing but digits")
    return "".join(map(str, digits)) + str(check_digit(payload))
