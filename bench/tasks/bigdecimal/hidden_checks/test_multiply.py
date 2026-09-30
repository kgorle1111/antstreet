import decimal

import pytest
from bigdecimal import multiply

CTX = decimal.Context(prec=5000, traps=[decimal.Inexact])


def expected_product(a, b):
    product = CTX.multiply(decimal.Decimal(a), decimal.Decimal(b))
    return "0" if product == 0 else format(product.normalize(CTX), "f")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("2", "3", "6"),
        ("99", "99", "9801"),
        ("12.5", "0.4", "5"),
        ("2.5", "4", "10"),
        ("0.5", "0.5", "0.25"),
        ("0.1", "0.1", "0.01"),
        ("0.001", "0.001", "0.000001"),
        ("1", "123.4500", "123.45"),
        ("100", "0.01", "1"),
        ("10", "10", "100"),
        ("1.5", "1.5", "2.25"),
    ],
)
def test_ordinary_products(a, b, expected):
    assert multiply(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("-1.5", "-2", "3"),
        ("-1.5", "2", "-3"),
        ("1.5", "-2", "-3"),
        ("-0.5", "0.5", "-0.25"),
        ("-0.001", "0.001", "-0.000001"),
    ],
)
def test_signs(a, b, expected):
    assert multiply(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("0", "123.45"),
        ("123.45", "0"),
        ("-0", "5"),
        ("-5", "0"),
        ("-5", "0.000"),
        ("0.000", "-0.0"),
        ("-" + "9" * 40, "0"),
        ("0", "0"),
    ],
)
def test_a_zero_factor_gives_plain_zero(a, b):
    assert multiply(a, b) == "0"


def test_trailing_zeros_of_the_integer_part_are_kept():
    assert multiply("1" + "0" * 30, "1" + "0" * 30) == "1" + "0" * 60
    assert multiply("25", "4") == "100"
    assert multiply("5", "2") == "10"
    assert multiply("1200", "3") == "3600"


def test_carries_and_long_products():
    assert multiply("9" * 50, "9" * 50) == expected_product("9" * 50, "9" * 50)
    assert multiply("999999999999", "999999999999") == "999999999998000000000001"
    assert multiply("123456789" * 6, "987654321" * 6) == expected_product(
        "123456789" * 6, "987654321" * 6
    )


def test_scales_add_up():
    assert multiply("0." + "0" * 29 + "1", "0." + "0" * 29 + "1") == "0." + "0" * 59 + "1"
    assert multiply("123.456", "0.001") == "0.123456"
    assert multiply("0.00000000000000000001", "100000000000000000000") == "1"


def test_repeated_products_stay_exact():
    power = "1"
    for _ in range(200):
        power = multiply(power, "2")
    assert power == str(2**200)
    factorial = "1"
    for n in range(2, 61):
        factorial = multiply(factorial, str(n))
    assert (
        factorial
        == "8320987112741390144276341183223364380754172606361245952449277696409600000000000000"
    )
