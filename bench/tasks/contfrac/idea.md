Create a Python module `contfrac.py` (standard library only) for continued fractions of rational
numbers, with four functions:

    continued_fraction(numerator: int, denominator: int) -> list[int]
    from_continued_fraction(terms: list[int]) -> tuple[int, int]
    convergents(terms: list[int]) -> list[tuple[int, int]]
    best_approximation(numerator: int, denominator: int, max_denominator: int) -> tuple[int, int]

A continued fraction `[a0, a1, a2, ..., ak]` stands for `a0 + 1/(a1 + 1/(a2 + ... + 1/ak))`.
`a0` is any int and every later term is an int of at least 1.

1. `continued_fraction(n, d)` returns the terms of the number `n / d` by Euclid's algorithm: `a0` is
   the floor of `n / d` (so it is negative for a negative number and `-4` for `-7/2`), and the
   rest are the quotients that follow. The signs of `n` and `d` may be anything (`d` negative
   works as if both signs were flipped), and `n / d` need not be in lowest terms. The result is
   always the form whose last term is at least 2 when there is more than one term, never the
   equal form ending in 1. `415/93` is `[4, 2, 6, 7]`, `-7/2` is `[-4, 2]`, `7/-3` is
   `[-3, 1, 2]`, `1/2` is `[0, 2]`, `3/1` is `[3]`, `0/5` is `[0]` and `6/4` is `[1, 2]`. A
   zero denominator raises `ValueError`.
2. `from_continued_fraction(terms)` returns the value as `(numerator, denominator)` in lowest terms
   with a positive denominator: `[4, 2, 6, 7]` is `(415, 93)`, `[-4, 2]` is `(-7, 2)`, `[1, 1]`
   is `(2, 1)` (a last term of 1 is accepted), `[0, 2]` is `(1, 2)` and `[5]` is `(5, 1)`.
3. `convergents(terms)` returns the list of `(numerator, denominator)` of the values of the first
   term, the first two terms, the first three, and so on, each in lowest terms with a positive
   denominator. `convergents([4, 2, 6, 7])` is `[(4, 1), (9, 2), (58, 13), (415, 93)]` and
   `convergents([-4, 2])` is `[(-4, 1), (-7, 2)]`.
4. `best_approximation(n, d, max_denominator)` returns `(p, q)` with `1 <= q <= max_denominator`:
   the fraction `p/q` that is closest to `n/d` (the smallest `|n/d - p/q|`), in lowest terms. If
   several are equally close, the one with the smaller `q` wins, and if `q` is equal as well, the
   smaller `p`. When `n/d` itself can be written with a denominator of at most `max_denominator`
   it is returned (in lowest terms). The closest fraction is not always a convergent. For
   `314159265/100000000` (3.14159265) the results are `(3, 1)` for `max_denominator` 1, `(13, 4)`
   for 4, `(22, 7)` for 7 and for every value up to 56, `(179, 57)` for 57, `(311, 99)` for 99 and
   `(355, 113)` for 113 and for 1000. Other examples: `(3, 2, 1)` gives `(1, 1)` (1 and 2 are
   equally far from 1.5, so the smaller wins), `(-3, 2, 1)` gives `(-2, 1)` and `(1, 3, 2)` gives
   `(1, 2)`. The sign of the result is in `p`, and a negative `d` works as if both signs were
   flipped. A very large `max_denominator` (like `10**40`) and very long `n` and `d` must be fast.
5. `n`, `d`, `max_denominator` and every term must be an int (a `bool` is not one), else
   `TypeError`; `terms` that is not a list or tuple raises `TypeError`. Empty `terms`, a term after
   the first that is below 1, a zero denominator `d` and a `max_denominator` below 1 raise
   `ValueError`. All arithmetic is exact: nothing goes through floating point.
