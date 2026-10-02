Create a Python module `fracmath.py` (standard library only) for exact arithmetic on fractions
written as text, with four functions:

    parse_fraction(text: str) -> tuple[int, int]
    format_fraction(numerator: int, denominator: int) -> str
    add(a: str, b: str) -> str
    divide(a: str, b: str) -> str

Parsing:

1. `parse_fraction` accepts three forms, with optional whitespace around the whole text: a whole
   number (`5`), a fraction (`3/4`, `6/4`), and a mixed number, which is a whole number, one or
   more spaces or tabs, and a fraction (`1 1/2`). Numbers are one or more ASCII digits and leading
   zeros are fine (`007`, `03/04`).
2. A single `-` directly in front of the first digit makes the whole value negative. For a mixed
   number it applies to the entire value, so `-1 1/2` is minus one and a half, which is -3/2, and
   `-0 1/2` is -1/2.
3. In a mixed number the fraction part must be proper: its numerator must be smaller than its
   denominator, so `1 1/2` and `1 0/5` are valid and `1 2/2`, `1 5/3` are not.
4. The result is a tuple `(numerator, denominator)` of ints in lowest terms: the denominator is
   always positive, the sign (if any) is on the numerator, and zero is `(0, 1)`. So `3/4` is
   `(3, 4)`, `6/4` is `(3, 2)`, `4/2` is `(2, 1)`, `0/5` and `-0` are `(0, 1)`, and `-1 1/2` is
   `(-3, 2)`.
5. `parse_fraction` raises `ValueError` for anything else: the empty string or only whitespace, a
   zero denominator (`1/0`, `0/0`, `1 1/0`), a sign anywhere but the very front (`3/-4`, `+1/2`,
   `1 -1/2`, `--1`), whitespace between the sign and the digits (`- 1/2`), whitespace around the
   slash (`1 / 2`, `1/ 2`), decimals (`1.5`, `0.5/2`), a mixed number whose whole part has a sign
   or a decimal, and any other characters. Non-ASCII digits are not digits. Input that is not a
   `str` raises `TypeError`.

Formatting:

6. `format_fraction(numerator, denominator)` takes two ints in any combination of signs and not
   necessarily in lowest terms, and returns the canonical text of the value. A zero denominator
   raises `ValueError`; an argument that is not an `int` (a `bool` is not one) raises `TypeError`.
7. The canonical text is built from the value in lowest terms: a whole number as just its digits
   (`3`, `-2`, `0`); a fraction smaller than one in size as `n/d` (`3/4`, `-3/4`); and anything
   else as a mixed number, the whole part then a single space then the proper fraction
   (`1 1/2`, `-3 1/2`). The `-` always comes first and a zero value never has a sign.
   `(6, 4)` is `1 1/2`, `(-7, 2)` is `-3 1/2`, `(4, 2)` is `2`, `(0, -5)` is `0`, `(1, -2)` is
   `-1/2` and `(-1, -2)` is `1/2`.

Arithmetic:

8. `add(a, b)` parses both texts, adds them exactly and returns the canonical text of the sum:
   `add("1/2", "1/3")` is `5/6`, `add("1/2", "1/2")` is `1`, `add("3/4", "3/4")` is `1 1/2` and
   `add("-1 1/2", "1/2")` is `-1`.
9. `divide(a, b)` returns the canonical text of `a / b`: `divide("1/2", "1/4")` is `2`,
   `divide("3", "2")` is `1 1/2` and `divide("-1 1/2", "3/4")` is `-2`. If `b` is zero it raises
   `ValueError` (not `ZeroDivisionError`).
10. `add` and `divide` raise `ValueError` for text `parse_fraction` rejects and `TypeError` for an
   argument that is not a `str`. All arithmetic is exact, however large the numbers: nothing goes
   through floating point.
