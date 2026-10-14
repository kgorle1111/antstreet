from itertools import product

from roman import from_roman, to_roman


def test_accepts_exactly_the_canonical_numerals():
    canonical = {to_roman(n): n for n in range(1, 4000)}
    # Exact str keys, so the lookup below runs no product code; `is` is not guarded, so the loop
    # does not walk this dict on every comparison.
    assert all(type(key) is str for key in canonical)
    for length in range(1, 6):
        for letters in product("IVXLCDM", repeat=length):
            s = "".join(letters)
            expected = canonical.get(s)
            if expected is not None:
                assert from_roman(s) == expected, s
            else:
                try:
                    result = from_roman(s)
                except ValueError:
                    continue
                raise AssertionError(f"{s!r} is not canonical but gave {result}")
