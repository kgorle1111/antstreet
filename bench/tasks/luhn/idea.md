Create a Python module `luhn.py` (standard library only) that validates numbers with the Luhn
check and computes Luhn check digits. It provides three functions:

    is_valid(text: str) -> bool
    check_digit(payload: str) -> int
    with_check_digit(payload: str) -> str

The Luhn check:

1. Take the digits of the number. Starting from the rightmost digit and moving left, leave the
   first digit as it is, double the second, leave the third, double the fourth, and so on (every
   second digit, starting with the second from the right, is doubled). If doubling gives a
   number above 9, subtract 9 from it. Add up all the resulting values. The number is valid when
   that sum is divisible by 10. For example `79927398713` is valid and `79927398710` is not, and
   `18` is valid because 1 doubled is 2 and 2 + 8 is 10.

Input text:

2. Spaces and hyphens may appear anywhere in the text, any number of them, also at the start and
   the end, and they are ignored: `4111 1111 1111 1111`, `4111-1111-1111-1111` and
   `  4111111111111111  ` are the same number. After they are removed, only the ASCII digits 0-9
   may remain. Any other character (a letter, a tab or newline, a dot, a plus sign, an
   underscore, a digit of another script such as `٣` or a full-width `３`) makes the text
   invalid.

The functions:

3. `is_valid(text)` returns `True` or `False` and never raises for a `str`. It returns `False`
   for text with invalid characters, and for text with fewer than two digits (none, or just
   one, so `0` and the empty string are `False`). It is `True` when the Luhn check of rule 1
   holds, so `00` and `0000 0000` are valid.
4. `check_digit(payload)` returns the single digit (an int from 0 to 9) that has to be appended
   to the right of the payload digits so that the result is valid. For `7992739871` it is 3, for
   `0` it is 0, for `5` it is 9. The payload follows rule 2 and needs at least one digit. Exactly
   one digit works for any payload.
5. `with_check_digit(payload)` returns the payload digits, with spaces and hyphens removed,
   followed by the check digit, as a `str`: `7992 7398-71` gives `79927398713`.
6. `check_digit` and `with_check_digit` raise `ValueError` for a payload that has no digits (the
   empty string, only spaces or hyphens) or has an invalid character. All three functions raise
   `TypeError` for an argument that is not a `str`.
