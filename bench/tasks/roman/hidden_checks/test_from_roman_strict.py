from itertools import product

from roman import from_roman, to_roman


def test_accepts_exactly_the_canonical_numerals():
    canonical = {to_roman(n): n for n in range(1, 4000)}
    for length in range(1, 6):
        for letters in product("IVXLCDM", repeat=length):
            s = "".join(letters)
            if s in canonical:
                assert from_roman(s) == canonical[s], s
            else:
                try:
                    result = from_roman(s)
                except ValueError:
                    continue
                raise AssertionError(f"{s!r} is not canonical but gave {result}")
