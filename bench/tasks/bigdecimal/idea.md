Create a Python module `bigdecimal.py` (standard library only) that does exact arithmetic on decimal
numbers of any size, passed and returned as strings:

    add(a: str, b: str) -> str
    subtract(a: str, b: str) -> str
    multiply(a: str, b: str) -> str
    compare(a: str, b: str) -> int

`add` returns a + b, `subtract` returns a - b, `multiply` returns a * b, all exactly (no rounding,
no precision limit). `compare` returns -1 if a < b, 0 if a == b and 1 if a > b.

The numbers can have hundreds of digits, far beyond what a float holds. So the implementation must do
the arithmetic itself on the digits. It must not convert a whole operand with `int()`, `float()`, the
`decimal` module or the `fractions` module, and must not use any other big-number library. Converting
a single digit character to a number, and ordinary arithmetic on single digits, is fine.

1. An input string has an optional leading `-`, then one or more digits, then optionally a `.`
   followed by one or more digits. Digits are only the ASCII characters `0` to `9`. Leading zeros are
   allowed (`"007"`, `"-000.50"`), trailing zeros after the point are allowed (`"1.500"`), and `"-0"`
   and `"-0.0"` are valid and mean zero.
2. Anything else raises `ValueError`. That includes the empty string, `"-"`, `"+5"`, `"1."`, `".5"`,
   `"-.5"`, `"1e5"`, `"1.2.3"`, `"--5"`, `"1_000"`, `"NaN"`, strings with any whitespace anywhere
   (`" 5"`, `"5 "`, `"5\n"`, `"1 000"`), digits that are not ASCII 0-9 (such as Arabic-Indic digits),
   and any value that is not a `str` (`5`, `1.5`, `None`, `b"5"`).
3. All four functions validate both arguments before doing anything else, so an invalid argument
   raises `ValueError` even if the other one is `"0"`, and whichever argument is the invalid one.
4. Results are canonical. There are no leading zeros: the integer part has no leading zeros, except
   that a number below 1 has a single `0` before the point (`"0.25"`, never `".25"` or `"00.25"`).
   There are no trailing zeros after the decimal point, and if nothing is left after the point the
   point is dropped as well (`"3"`, never `"3."` or `"3.0"`). A negative result starts with `-`
   directly followed by the canonical form of its absolute value (`"-0.5"`).
5. Zero is always returned as `"0"`, never `"-0"`, `"0.0"` or `"00"`. This includes `"5" - "5"`, a
   product where either factor is zero (even a negative one), and the sum of `"-0"` and `"-0.00"`.
6. Results are exact for any operand size and any mix of scales: `add("0.1", "0.2")` is `"0.3"`,
   `add("0.999", "0.001")` is `"1"`, `subtract("1", "0.000000000000000000000001")` is
   `"0.999999999999999999999999"`, `multiply("12.5", "0.4")` is `"5"`, `multiply("-0.001", "0.001")`
   is `"-0.000001"`, and `add("99999999999999999999", "1")` is `"100000000000000000000"`.
7. Signs follow ordinary arithmetic: adding numbers of opposite sign subtracts their magnitudes and
   takes the sign of the larger one, subtracting a number adds its negation, and a product is
   negative only when exactly one factor is negative and the product is not zero.
8. `compare` compares numeric values, not text. Leading and trailing zeros do not matter
   (`compare("1.50", "01.5")` is 0), `"-0"` equals `"0"`, `"9"` is less than `"10"`, `"-9"` is greater
   than `"-10"`, and two numbers with hundreds of digits that differ only in the last digit compare
   correctly. It returns exactly `-1`, `0` or `1`.
