from roman import from_roman, to_roman


def test_from_roman_inverts_to_roman_for_every_number():
    for n in range(1, 4000):
        assert from_roman(to_roman(n)) == n, n
