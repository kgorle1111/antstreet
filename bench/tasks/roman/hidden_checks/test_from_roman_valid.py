import pytest
from roman import from_roman


@pytest.mark.parametrize(
    ("s", "expected"),
    [
        ("I", 1),
        ("III", 3),
        ("IV", 4),
        ("V", 5),
        ("IX", 9),
        ("XIV", 14),
        ("XL", 40),
        ("LVIII", 58),
        ("XC", 90),
        ("CD", 400),
        ("CM", 900),
        ("M", 1000),
        ("MCMXCIV", 1994),
        ("MMXXIV", 2024),
        ("MMMDCCCLXXXVIII", 3888),
        ("MMMCMXCIX", 3999),
    ],
)
def test_canonical_numerals(s, expected):
    result = from_roman(s)
    assert result == expected
    assert type(result) is int
