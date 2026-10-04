import pytest
from baseconv import convert


@pytest.mark.parametrize(
    ("text", "src", "dst", "max_frac", "expected"),
    [
        ("-1.5", 10, 2, 10, "-1.1"),
        ("-0", 10, 2, 10, "0"),
        ("-0.0001", 10, 2, 3, "0"),
        ("-0.0", 10, 10, 10, "0"),
        ("-0.5", 10, 2, 0, "0"),
        ("-1.9", 10, 10, 0, "-1"),
        ("-0.0001", 10, 2, 14, "-0.00000000000001"),
        ("-0.0001", 10, 2, 13, "0"),
        ("-ff", 16, 10, 10, "-255"),
        ("-255", 10, 16, 10, "-ff"),
        ("-10", 2, 10, 10, "-2"),
        ("-0.1", 2, 10, 10, "-0.5"),
        ("-000", 10, 10, 10, "0"),
        ("-00.00", 8, 16, 10, "0"),
        ("-0.99", 10, 10, 1, "-0.9"),
        ("-0.09", 10, 10, 1, "0"),
        ("-0.09", 10, 10, 2, "-0.09"),
    ],
)
def test_signs(text, src, dst, max_frac, expected):
    assert convert(text, src, dst, max_frac) == expected


def test_a_value_cut_down_to_zero_has_no_sign_but_a_one_digit_more_keeps_it():
    assert convert("-0.3", 10, 2, 1) == "0"
    assert convert("-0.3", 10, 2, 2) == "-0.01"
    assert convert("-0.3", 10, 2, 0) == "0"


def test_the_sign_goes_in_front_of_a_value_below_one():
    assert convert("-0.5", 10, 2) == "-0.1"
    assert not convert("-0.5", 10, 2).startswith("0")


def test_negative_and_positive_have_the_same_digits():
    for text in ("12.34", "0.1", "255", "0.999", "7.5"):
        for dst in (2, 7, 16, 36):
            assert convert("-" + text, 10, dst, 6) == "-" + convert(text, 10, dst, 6)
