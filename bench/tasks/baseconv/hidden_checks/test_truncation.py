import pytest
from baseconv import convert


@pytest.mark.parametrize(
    ("text", "src", "dst", "max_frac", "expected"),
    [
        ("0.1", 10, 2, 8, "0.00011001"),
        ("0.1", 10, 2, 0, "0"),
        ("0.9", 10, 2, 0, "0"),
        ("2.9", 10, 10, 0, "2"),
        ("0.999999", 10, 10, 3, "0.999"),
        ("0.6", 10, 2, 1, "0.1"),
        ("0.6", 10, 2, 2, "0.1"),
        ("1", 10, 2, 5, "1"),
        ("0.1", 3, 10, 3, "0.333"),
        ("0.2", 3, 10, 3, "0.666"),
        ("0.1", 3, 10, 11, "0.33333333333"),
        ("0.2", 3, 10, 12, "0.666666666666"),
        ("0.5", 10, 2, 50, "0.1"),
        ("1.1", 10, 2, 4, "1.0001"),
        ("0.1", 10, 2, 1, "0"),
        ("0.1", 10, 2, 3, "0"),
        ("0.1", 10, 2, 4, "0.0001"),
        ("0.1", 10, 2, 5, "0.00011"),
        ("0.1", 10, 2, 6, "0.00011"),
        ("7.99", 10, 10, 1, "7.9"),
        ("0.99", 10, 16, 2, "0.fd"),
    ],
)
def test_cut_off_never_rounded(text, src, dst, max_frac, expected):
    assert convert(text, src, dst, max_frac) == expected


def test_max_frac_is_a_keyword_or_third_positional_argument():
    assert convert("0.1", 10, 2, max_frac=4) == "0.0001"
    assert convert("0.1", 10, 2, 4) == "0.0001"


def test_the_default_is_ten_digits():
    assert convert("0.1", 3, 10) == convert("0.1", 3, 10, 10) == convert("0.1", 3, 10, max_frac=10)
    assert len(convert("0.1", 3, 10).split(".")[1]) == 10
    assert len(convert("0.1", 3, 10, 11).split(".")[1]) == 11


def test_a_whole_number_is_not_affected_by_max_frac():
    for limit in (0, 1, 10, 100):
        assert convert("255", 10, 16, limit) == "ff"
        assert convert("12.0", 10, 2, limit) == "1100"
