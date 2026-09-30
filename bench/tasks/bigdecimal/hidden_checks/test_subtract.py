import decimal

import pytest
from bigdecimal import subtract

CTX = decimal.Context(prec=5000, traps=[decimal.Inexact])


def expected_difference(a, b):
    diff = CTX.subtract(decimal.Decimal(a), decimal.Decimal(b))
    return "0" if diff == 0 else format(diff.normalize(CTX), "f")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("3", "1", "2"),
        ("0.3", "0.1", "0.2"),
        ("10", "0.001", "9.999"),
        ("100.00", "99.99", "0.01"),
        ("1", "2", "-1"),
        ("0.1", "0.30", "-0.2"),
        ("0", "5", "-5"),
        ("0", "-5", "5"),
        ("5", "0", "5"),
        ("-1", "-2", "1"),
        ("-1", "2", "-3"),
        ("1", "-2", "3"),
        ("-2.5", "-2.5", "0"),
    ],
)
def test_ordinary_differences(a, b, expected):
    assert subtract(a, b) == expected


def test_borrow_ripples_through_every_digit():
    assert subtract("1" + "0" * 40, "1") == "9" * 40
    assert subtract("1", "0." + "0" * 23 + "1") == "0." + "9" * 24
    assert subtract("1000000000000000000000", "0.000000000000000000001") == (
        "999999999999999999999.999999999999999999999"
    )


def test_result_sign_follows_the_larger_magnitude():
    assert subtract("0.001", "0.002") == "-0.001"
    assert subtract("-0.001", "-0.002") == "0.001"
    assert subtract("12345678901234567890", "12345678901234567891") == "-1"
    assert subtract("12345678901234567891", "12345678901234567890") == "1"


def test_equal_numbers_in_any_spelling_give_plain_zero():
    for a, b in [("5", "5"), ("1.50", "01.5"), ("-0", "0"), ("0", "-0.000"), ("-7.7", "-7.70")]:
        assert subtract(a, b) == "0"


def test_swapping_operands_negates_the_result():
    samples = ["0", "1", "-1", "0.5", "-12.75", "10" * 15 + ".01"]
    for a in samples:
        for b in samples:
            forward = subtract(a, b)
            assert forward == expected_difference(a, b)
            backward = subtract(b, a)
            assert backward == expected_difference(b, a)
            assert forward == "0" or forward == ("-" + backward).replace("--", "")


def test_exact_where_floats_are_not():
    assert subtract("9007199254740993", "9007199254740992") == "1"
    assert subtract("0.3", "0.1") == "0.2"
    assert (
        subtract("1.00000000000000000000000000000001", "1") == "0.00000000000000000000000000000001"
    )
