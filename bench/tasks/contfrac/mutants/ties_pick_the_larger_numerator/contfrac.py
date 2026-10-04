# When two fractions are equally close the larger one is returned instead of the one with the smaller p.
from fractions import Fraction


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {value!r}")
    return value


def _terms(terms: object) -> list[int]:
    if not isinstance(terms, list | tuple):
        raise TypeError("terms must be a list of ints")
    if not terms:
        raise ValueError("a continued fraction needs at least one term")
    checked = [_int(t, "a term") for t in terms]
    if any(t < 1 for t in checked[1:]):
        raise ValueError("every term after the first must be at least 1")
    return checked


def _ratio(numerator: object, denominator: object) -> tuple[int, int]:
    n, d = _int(numerator, "numerator"), _int(denominator, "denominator")
    if d == 0:
        raise ValueError("the denominator must not be zero")
    return (-n, -d) if d < 0 else (n, d)


def continued_fraction(numerator: int, denominator: int) -> list[int]:
    n, d = _ratio(numerator, denominator)
    terms = []
    while d:
        q, r = divmod(n, d)
        terms.append(q)
        n, d = d, r
    return terms


def from_continued_fraction(terms: list[int]) -> tuple[int, int]:
    checked = _terms(terms)
    num, den = checked[-1], 1
    for t in reversed(checked[:-1]):
        num, den = t * num + den, num
    return num, den


def convergents(terms: list[int]) -> list[tuple[int, int]]:
    out = []
    p_prev, p, q_prev, q = 0, 1, 1, 0
    for a in _terms(terms):
        p_prev, p = p, a * p + p_prev
        q_prev, q = q, a * q + q_prev
        out.append((p, q))
    return out


def best_approximation(numerator: int, denominator: int, max_denominator: int) -> tuple[int, int]:
    n, d = _ratio(numerator, denominator)
    limit = _int(max_denominator, "max_denominator")
    if limit < 1:
        raise ValueError("max_denominator must be at least 1")
    x = Fraction(n, d)
    if x.denominator <= limit:
        return x.numerator, x.denominator
    xn, xd = x.numerator, x.denominator
    a, b = x.numerator // x.denominator, 1  # lo = a/b is below x
    c, e = a + 1, 1  # hi = c/e is above x
    while b + e <= limit:
        if Fraction(a + c, b + e) < x:
            # largest k with (a + k*c)/(b + k*e) < x, within the denominator limit
            k = (xn * b - a * xd - 1) // (c * xd - xn * e)
            k = min(k, (limit - b) // e)
            a, b = a + k * c, b + k * e
        else:
            k = (c * xd - xn * e - 1) // (xn * b - a * xd)
            k = min(k, (limit - e) // b)
            c, e = c + k * a, e + k * b
    below, above = x - Fraction(a, b), Fraction(c, e) - x
    if below < above or (below == above and (b, a) >= (e, c)):
        return a, b
    return c, e
