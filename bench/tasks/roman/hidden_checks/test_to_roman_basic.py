import pytest
from roman import to_roman


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "I"),
        (2, "II"),
        (3, "III"),
        (5, "V"),
        (6, "VI"),
        (8, "VIII"),
        (10, "X"),
        (14, "XIV"),
        (27, "XXVII"),
        (58, "LVIII"),
        (100, "C"),
        (500, "D"),
        (1000, "M"),
        (1987, "MCMLXXXVII"),
        (2024, "MMXXIV"),
        (3000, "MMM"),
    ],
)
def test_ordinary_numbers(n, expected):
    assert to_roman(n) == expected


def test_result_is_a_str():
    assert isinstance(to_roman(12), str)
