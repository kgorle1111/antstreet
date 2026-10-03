Create a Python module `baseconv.py` (standard library only) that converts numbers written in one
base to another, fractional digits included, with two functions:

    parse_number(text: str, base: int) -> Fraction
    convert(text: str, from_base: int, to_base: int, max_frac: int = 10) -> str

1. A base is an int from 2 to 36. The digits are `0` to `9` and then the letters `a` to `z` for 10
   to 35. Input may use upper or lower case letters; output always uses lower case.
2. The text of a number is: an optional single `-`, then one or more digits, then optionally a `.`
   followed by one or more digits. Nothing else is allowed: no spaces anywhere (not even around
   the text), no `+`, no underscores, no `.5` or `5.` (a point needs digits on both sides), no
   exponent and no other characters. Leading zeros are fine (`007`). Every digit must be smaller
   than the base (`2` is not a base-2 digit, `g` is not a base-16 digit).
3. `parse_number(text, base)` returns the exact value as a `fractions.Fraction`: `("ff.8", 16)` is
   `Fraction(511, 2)`, `("-0.1", 2)` is `Fraction(-1, 2)`, `("007", 10)` is `Fraction(7)` and
   `("Z", 36)` is `Fraction(35)`. `"-0"` gives `Fraction(0)`.
4. `convert(text, from_base, to_base, max_frac=10)` reads the number in `from_base` and returns it
   written in `to_base` as text. Rules for the output:
   - The whole part is written without leading zeros, and as `0` when it is zero.
   - The fractional part is worked out digit by digit (multiply by `to_base`, the whole part of
     the product is the next digit, repeat with the rest) until the rest is zero or `max_frac`
     digits have been produced. The digits are cut off there, never rounded.
   - Trailing zeros of the fractional digits are then removed, and when no fractional digit is
     left there is no `.` at all.
   - A `-` goes in front only when the value is negative and what is written is not zero. A
     negative number that is cut down to nothing is written as `0`, without a sign.
   - `max_frac` is an int of at least 0; `0` means no fractional digits.
5. Examples: `convert("255", 10, 16)` is `"ff"`, `convert("ff", 16, 2)` is `"11111111"`,
   `convert("10.01", 2, 10)` is `"2.25"`, `convert("-ff.8", 16, 10)` is `"-255.5"`,
   `convert("0.5", 10, 2)` is `"0.1"`, `convert("0.1", 10, 2)` is `"0.000110011"` (the tenth digit
   is a zero, which is removed), `convert("0.1", 10, 2, 8)` is `"0.00011001"`,
   `convert("0.1", 3, 10)` is `"0.3333333333"`, `convert("-0", 10, 2)` is `"0"` and
   `convert("-0.0001", 10, 2, 3)` is `"0"`.
6. Text that does not follow rule 2, or that has a digit not smaller than its base, raises
   `ValueError`. A `text` that is not a `str` raises `TypeError`. A base outside 2 to 36 and a
   negative `max_frac` raise `ValueError`; a base or `max_frac` that is not an int (a `bool` is not
   one) raises `TypeError`. Parsing is exact however long the number is: nothing goes through
   floating point.
