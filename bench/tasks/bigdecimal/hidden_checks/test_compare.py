import decimal

import pytest
from bigdecimal import compare


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("1", "2", -1),
        ("2", "1", 1),
        ("1", "1", 0),
        ("9", "10", -1),
        ("10", "9", 1),
        ("2.5", "10.5", -1),
        ("0.5", "0.25", 1),
        ("0.09", "0.1", -1),
        ("10", "9.99", 1),
        ("0.1", "0.10000000000000000000000001", -1),
    ],
)
def test_positive_numbers_compare_by_value_not_by_text(a, b, expected):
    assert compare(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("-1", "1", -1),
        ("1", "-1", 1),
        ("-9", "-10", 1),
        ("-10", "-9", -1),
        ("-10", "-9.99", -1),
        ("-0.0001", "0", -1),
        ("0", "0.0001", -1),
        ("-0.5", "-0.25", -1),
        ("-1000", "1", -1),
    ],
)
def test_negative_numbers(a, b, expected):
    assert compare(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1.50", "01.5"),
        ("007", "7.000"),
        ("-0", "0"),
        ("-0.000", "0.0"),
        ("0", "0.000"),
        ("-2.50", "-002.5"),
        ("100", "100.00"),
    ],
)
def test_equal_values_in_different_spellings_compare_equal(a, b):
    assert compare(a, b) == 0
    assert compare(b, a) == 0


def test_operands_with_hundreds_of_digits():
    big = "1" + "0" * 299
    assert compare(big + "1", big + "2") == -1
    assert compare(big + "2", big + "1") == 1
    assert compare(big + "1", big + "1") == 0
    tiny = "0." + "0" * 299
    assert compare(tiny + "1", tiny + "2") == -1
    assert compare("-" + tiny + "1", "-" + tiny + "2") == 1
    assert compare("9" * 300, "1" + "0" * 300) == -1
    assert compare("1" + "0" * 300 + ".0", "9" * 300) == 1


def test_agrees_with_decimal_on_a_grid_and_is_antisymmetric():
    samples = ["0", "-0", "1", "-1", "0.5", "-0.5", "10", "9.99", "-9.99", "0.05", "1.10", "1.9"]
    samples += ["12345678901234567890.5", "12345678901234567890.05", "-12345678901234567890.5"]
    for a in samples:
        for b in samples:
            x, y = decimal.Decimal(a), decimal.Decimal(b)
            expected = (x > y) - (x < y)
            assert compare(a, b) == expected, (a, b)
            assert compare(b, a) == -expected, (b, a)
