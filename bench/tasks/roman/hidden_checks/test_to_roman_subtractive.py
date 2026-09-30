import pytest
from roman import to_roman


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (4, "IV"),
        (9, "IX"),
        (40, "XL"),
        (90, "XC"),
        (400, "CD"),
        (900, "CM"),
    ],
)
def test_each_subtractive_pair(n, expected):
    assert to_roman(n) == expected


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (44, "XLIV"),
        (49, "XLIX"),
        (99, "XCIX"),
        (444, "CDXLIV"),
        (949, "CMXLIX"),
        (999, "CMXCIX"),
        (1444, "MCDXLIV"),
        (1994, "MCMXCIV"),
        (3888, "MMMDCCCLXXXVIII"),
        (3999, "MMMCMXCIX"),
    ],
)
def test_pairs_combined_across_places(n, expected):
    assert to_roman(n) == expected
