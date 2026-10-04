import pytest
from baseconv import convert


@pytest.mark.parametrize(
    ("text", "src", "dst", "expected"),
    [
        ("255", 10, 16, "ff"),
        ("ff", 16, 2, "11111111"),
        ("0", 10, 2, "0"),
        ("10", 2, 10, "2"),
        ("1295", 10, 36, "zz"),
        ("zz", 36, 10, "1295"),
        ("777", 8, 10, "511"),
        ("11111111", 2, 16, "ff"),
        ("FF", 16, 10, "255"),
        ("1000", 10, 2, "1111101000"),
        ("007", 10, 10, "7"),
        ("0000", 10, 2, "0"),
        ("1", 2, 36, "1"),
        ("z", 36, 2, "100011"),
        ("Hello", 36, 10, "29234652"),
        ("29234652", 10, 36, "hello"),
        ("10", 36, 10, "36"),
        ("10", 10, 36, "a"),
        ("35", 10, 36, "z"),
        ("36", 10, 36, "10"),
    ],
)
def test_whole_numbers(text, src, dst, expected):
    assert convert(text, src, dst) == expected


def test_a_very_long_number_is_exact():
    assert convert("1" + "0" * 50, 10, 16) == format(10**50, "x")
    assert convert(format(10**50, "x"), 16, 10) == "1" + "0" * 50
    assert convert("9" * 60, 10, 2) == format(int("9" * 60), "b")
    assert convert("f" * 40, 16, 2) == "1" * 160


def test_zero_in_every_base_is_just_zero():
    for base in (2, 3, 10, 16, 36):
        assert convert("0", base, base) == "0"
        assert convert("000", base, 2) == "0"


def test_the_same_base_returns_the_number_without_leading_zeros_in_lower_case():
    assert convert("00AbC", 16, 16) == "abc"
    assert convert("0012", 10, 10) == "12"


def test_a_whole_number_never_gets_a_point():
    assert convert("12", 10, 2) == "1100"
    assert convert("12.0", 10, 2) == "1100"
    assert convert("12.000", 10, 16) == "c"
