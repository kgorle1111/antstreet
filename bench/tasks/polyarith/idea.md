Create a Python module `polyarith.py` (standard library only) for polynomials in one variable with
exact rational coefficients, with seven functions:

    poly_add(p: list, q: list) -> list[Fraction]
    poly_mul(p: list, q: list) -> list[Fraction]
    poly_divmod(p: list, q: list) -> tuple[list[Fraction], list[Fraction]]
    poly_eval(p: list, x: int | Fraction) -> Fraction
    poly_derivative(p: list) -> list[Fraction]
    poly_gcd(p: list, q: list) -> list[Fraction]
    poly_str(p: list) -> str

1. A polynomial is a list (or tuple) of coefficients, lowest degree first: `[1, 2, 3]` is
   `1 + 2x + 3x^2`. A coefficient is an `int` or a `fractions.Fraction`. Inputs may end in zeros
   (`[1, 0, 0]` is the polynomial `1`) and `[]` and `[0, 0]` are both the zero polynomial.
2. Every function that returns a polynomial returns a list of `Fraction`s with no trailing zero
   coefficients, so the last entry is the leading coefficient and the zero polynomial is `[]`.
   `poly_add([1, 2], [3, -2])` is `[Fraction(4)]` and `poly_add([1, 1], [-1, -1])` is `[]`.
3. `poly_mul` multiplies, exactly: `poly_mul([1, 1], [1, 1])` is `[1, 2, 1]` (as Fractions), and
   anything times the zero polynomial is `[]`.
4. `poly_divmod(p, q)` returns `(quotient, remainder)` from polynomial long division, so that
   `p == quotient * q + remainder` and the remainder is the zero polynomial or has a smaller
   degree than `q`. Both are in the form of rule 2. If `p` has a smaller degree than `q` the
   quotient is `[]` and the remainder is `p`. For example `poly_divmod([-1, 0, 1], [1, 1])` (that
   is `x^2 - 1` divided by `x + 1`) is `([-1, 1], [])`, and `poly_divmod([1, 0, 0, 1], [1, 1])`
   is `([1, -1, 1], [])`. Dividing by the zero polynomial raises `ZeroDivisionError`.
5. `poly_eval(p, x)` returns the value of the polynomial at `x` as an exact `Fraction`: `[1, 2, 3]`
   at `2` is `Fraction(17)`, and the zero polynomial is `Fraction(0)` everywhere. `x` is an `int`
   or a `Fraction`.
6. `poly_derivative(p)` returns the derivative: `[5, 4, 3]` gives `[4, 6]`, and a constant or the
   zero polynomial gives `[]`.
7. `poly_gcd(p, q)` returns the greatest common divisor of the two polynomials, made monic (its
   leading coefficient is 1). Two polynomials with no common factor give `[Fraction(1)]`. If one
   argument is the zero polynomial the result is the other one made monic, and `poly_gcd([], [])`
   is `[]`. For example `poly_gcd([-1, 0, 1], [1, 2, 1])` (`x^2 - 1` and `(x+1)^2`) is `[1, 1]`.
8. `poly_str(p)` writes the polynomial from the highest degree down, leaving out terms whose
   coefficient is zero. The zero polynomial is `"0"`. A term is its coefficient's size, then `x`
   (degree 1) or `x^k` (degree k at least 2) and nothing for degree 0. The size is left out when
   it is 1 and the term has an `x`; a size that is a whole number is written in digits; a size
   that is not a whole number is written in parentheses as `(n/d)` in lowest terms, also for
   degree 0. The first term has a `-` directly in front when its coefficient is negative; every
   later term is joined with ` + ` or ` - ` (a space, the sign, a space) by the sign of its
   coefficient. So `[1, 2, 3]` is `"3x^2 + 2x + 1"`, `[1, -1]` is `"-x + 1"`, `[0, 0, 1]` is
   `"x^2"`, `[Fraction(-3, 2), 4]` is `"4x - (3/2)"`, `[0, Fraction(-1, 3)]` is `"-(1/3)x"` and
   `[-5]` is `"-5"`.
9. A polynomial argument that is not a list or tuple raises `TypeError`, and so does a coefficient
   that is not an `int` or a `Fraction` (a `float`, a `str` and a `bool` are rejected), and an `x`
   for `poly_eval` that is not an `int` or a `Fraction` (a `bool` is rejected there too). Every
   coefficient of every argument is checked, even where it would not change the result. All arithmetic is exact: nothing goes
   through floating point, however large the numbers.
