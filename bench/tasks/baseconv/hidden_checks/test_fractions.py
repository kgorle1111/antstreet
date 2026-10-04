import pytest
from baseconv import convert


@pytest.mark.parametrize(
    ("text", "src", "dst", "expected"),
    [
        ("0.5", 10, 2, "0.1"),
        ("0.75", 10, 2, "0.11"),
        ("10.01", 2, 10, "2.25"),
        ("-ff.8", 16, 10, "-255.5"),
        ("0.125", 10, 2, "0.001"),
        ("0.1", 2, 10, "0.5"),
        ("0.01", 2, 10, "0.25"),
        ("0.001", 2, 10, "0.125"),
        ("1.1", 2, 16, "1.8"),
        ("a.8", 16, 10, "10.5"),
        ("A.8", 16, 10, "10.5"),
        ("0.8", 16, 2, "0.1"),
        ("3.14", 10, 10, "3.14"),
        ("0.3", 10, 10, "0.3"),
        ("0.0625", 10, 2, "0.0001"),
        ("0.10", 10, 10, "0.1"),
        ("5.000", 10, 2, "101"),
        ("0.f", 16, 2, "0.1111"),
        ("2.4", 8, 10, "2.5"),
        ("0.4", 8, 2, "0.1"),
    ],
)
def test_exact_fractions(text, src, dst, expected):
    assert convert(text, src, dst) == expected


def test_a_number_below_one_starts_with_a_zero_before_the_point():
    assert convert("0.5", 10, 10) == "0.5"
    assert convert("0.01", 10, 10) == "0.01"
    assert not convert("0.5", 10, 2).startswith(".")


def test_endless_expansions_stop_at_ten_digits_by_default():
    assert convert("0.1", 3, 10) == "0.3333333333"
    assert convert("1.2", 3, 10) == "1.6666666666"
    assert convert("0.2", 3, 10) == "0.6666666666"
    assert convert("0.1", 10, 3) == "0.00220022"
    assert convert("0.1", 10, 2) == "0.000110011"


def test_trailing_zeros_left_by_the_cut_are_removed():
    # the tenth binary digit of one tenth is 0, so only nine digits remain
    assert convert("0.1", 10, 2) == "0.000110011"
    assert convert("0.123456789012", 10, 10) == "0.123456789"
    assert convert("0.1", 10, 3) == "0.00220022"


def test_input_trailing_zeros_make_no_difference():
    assert convert("0.500000", 10, 2) == convert("0.5", 10, 2) == "0.1"
    assert convert("1.50", 10, 16) == "1.8"


def test_output_digits_are_lower_case():
    assert convert("10.9", 10, 16) == "a.e666666666"
    assert convert("0.999", 10, 36, 3) == "0.zyp"
