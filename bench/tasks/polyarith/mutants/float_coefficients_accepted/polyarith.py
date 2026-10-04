# A float coefficient is accepted and converted, instead of raising TypeError.
from fractions import Fraction


def _poly(p: object) -> list[Fraction]:
    if not isinstance(p, list | tuple):
        raise TypeError("a polynomial must be a list of coefficients")
    out = []
    for c in p:
        if isinstance(c, bool) or not isinstance(c, int | Fraction | float):
            raise TypeError(f"a coefficient must be an int or a Fraction, got {c!r}")
        out.append(Fraction(c))
    return _trim(out)


def _trim(coeffs: list[Fraction]) -> list[Fraction]:
    while coeffs and coeffs[-1] == 0:
        coeffs.pop()
    return coeffs


def poly_add(p: list, q: list) -> list[Fraction]:
    a, b = _poly(p), _poly(q)
    n = max(len(a), len(b))
    a, b = a + [Fraction(0)] * (n - len(a)), b + [Fraction(0)] * (n - len(b))
    return _trim([x + y for x, y in zip(a, b, strict=True)])


def poly_mul(p: list, q: list) -> list[Fraction]:
    a, b = _poly(p), _poly(q)
    if not a or not b:
        return []
    out = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] += x * y
    return _trim(out)


def poly_divmod(p: list, q: list) -> tuple[list[Fraction], list[Fraction]]:
    a, b = _poly(p), _poly(q)
    if not b:
        raise ZeroDivisionError("division by the zero polynomial")
    quotient = [Fraction(0)] * max(len(a) - len(b) + 1, 0)
    while len(a) >= len(b):
        shift = len(a) - len(b)
        factor = a[-1] / b[-1]
        quotient[shift] = factor
        for i, c in enumerate(b):
            a[i + shift] -= factor * c
        _trim(a)
    return _trim(quotient), a


def poly_eval(p: list, x: int | Fraction) -> Fraction:
    a = _poly(p)
    if isinstance(x, bool) or not isinstance(x, int | Fraction):
        raise TypeError(f"x must be an int or a Fraction, got {x!r}")
    total = Fraction(0)
    for c in reversed(a):
        total = total * x + c
    return total


def poly_derivative(p: list) -> list[Fraction]:
    a = _poly(p)
    return _trim([i * c for i, c in enumerate(a)][1:])


def poly_gcd(p: list, q: list) -> list[Fraction]:
    a, b = _poly(p), _poly(q)
    while b:
        a, b = b, poly_divmod(a, b)[1]
    if not a:
        return []
    return [c / a[-1] for c in a]


def poly_str(p: list) -> str:
    a = _poly(p)
    if not a:
        return "0"
    parts = []
    for degree in range(len(a) - 1, -1, -1):
        c = a[degree]
        if c == 0:
            continue
        magnitude = abs(c)
        if magnitude.denominator != 1:
            number = f"({magnitude})"
        elif magnitude == 1 and degree > 0:
            number = ""
        else:
            number = str(magnitude)
        variable = "" if degree == 0 else "x" if degree == 1 else f"x^{degree}"
        parts.append((c < 0, number + variable))
    first_negative, first = parts[0]
    text = ("-" if first_negative else "") + first
    for negative, term in parts[1:]:
        text += (" - " if negative else " + ") + term
    return text
