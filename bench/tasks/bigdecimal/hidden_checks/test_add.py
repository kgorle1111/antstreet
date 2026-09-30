import decimal

import pytest
from bigdecimal import add

CTX = decimal.Context(prec=5000, traps=[decimal.Inexact])


def expected_sum(a, b):
    total = CTX.add(decimal.Decimal(a), decimal.Decimal(b))
    return "0" if total == 0 else format(total.normalize(CTX), "f")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("1", "2", "3"),
        ("0", "0", "0"),
        ("0.1", "0.2", "0.3"),
        ("12.50", "0.25", "12.75"),
        ("0.5", "0.5", "1"),
        ("0.999", "0.001", "1"),
        ("999.999", "0.001", "1000"),
        ("99999999999999999999", "1", "100000000000000000000"),
        ("9007199254740993", "1", "9007199254740994"),
        ("1.05", "0.05", "1.1"),
        ("100", "0.001", "100.001"),
    ],
)
def test_ordinary_sums(a, b, expected):
    assert add(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("-12.50", "0.25", "-12.25"),
        ("5", "-8", "-3"),
        ("-5", "8", "3"),
        ("-5", "-8", "-13"),
        ("-0.1", "-0.2", "-0.3"),
        ("-100", "100.5", "0.5"),
        ("0.001", "-1", "-0.999"),
    ],
)
def test_mixed_signs(a, b, expected):
    assert add(a, b) == expected


def test_operands_of_different_scales_and_lengths():
    assert add("123456789012345678901234567890.123456789", "0.000000000987654321") == (
        "123456789012345678901234567890.123456789987654321"
    )
    assert add("1", "0.0000000000000000000000000001") == "1.0000000000000000000000000001"
    assert add("0.5", "1000000000000000000000") == "1000000000000000000000.5"


def test_carry_ripples_through_every_digit():
    assert add("9" * 60, "1") == "1" + "0" * 60
    assert add("0." + "9" * 60, "0." + "0" * 59 + "1") == "1"
    assert add("9" * 30 + "." + "9" * 30, "0." + "0" * 29 + "1") == "1" + "0" * 30


def test_sum_is_commutative_and_zero_is_the_identity():
    samples = ["0", "1", "-1", "12.5", "-0.001", "99999999999999999999.99999999999999999999"]
    for a in samples:
        assert add(a, "0") == expected_sum(a, "0")
        assert add("0", a) == expected_sum(a, "0")
        for b in samples:
            assert add(a, b) == add(b, a) == expected_sum(a, b)


def test_a_number_plus_its_negation_is_zero():
    for a in ["1", "0.1", "123456789.987654321", "1" + "0" * 40 + ".5"]:
        assert add(a, "-" + a) == "0"
        assert add("-" + a, a) == "0"


def test_exact_where_floats_are_not():
    total = "0"
    for _ in range(1000):
        total = add(total, "0.1")
    assert total == "100"
    assert add("0.1000000000000000055511151231257827", "0.0000000000000000000000000000000001") == (
        "0.1000000000000000055511151231257828"
    )
