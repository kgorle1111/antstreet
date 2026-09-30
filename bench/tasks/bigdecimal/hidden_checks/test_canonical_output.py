import random
import re

import pytest
from bigdecimal import add, multiply, subtract

CANONICAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("007", "0", "7"),
        ("000.50", "0", "0.5"),
        ("-007.500", "0", "-7.5"),
        ("0000", "0001", "1"),
        ("00.25", "0", "0.25"),
        ("-0.05", "0", "-0.05"),
        ("0.0005", "0.0005", "0.001"),
    ],
)
def test_no_leading_zeros_and_a_single_zero_before_the_point(a, b, expected):
    assert add(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("1.500", "1.500", "3"),
        ("0.10", "0.20", "0.3"),
        ("2.50", "0", "2.5"),
        ("1.000", "0.000", "1"),
        ("0.5", "0.5", "1"),
        ("10.10", "0.90", "11"),
    ],
)
def test_no_trailing_zeros_and_no_dangling_point(a, b, expected):
    assert add(a, b) == expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("100", "0", "100"),
        ("1000", "0.000", "1000"),
        ("120.50", "0", "120.5"),
        ("2000.0", "1000.0", "3000"),
        ("90", "10", "100"),
        ("1" + "0" * 20, "0", "1" + "0" * 20),
    ],
)
def test_zeros_at_the_end_of_the_integer_part_are_significant(a, b, expected):
    assert add(a, b) == expected


def test_integer_results_with_trailing_zeros_from_subtract_and_multiply():
    assert subtract("2000.0", "1000.0") == "1000"
    assert subtract("5000", "0.5") == "4999.5"
    assert multiply("2000", "1.5") == "3000"
    assert multiply("0.5", "40") == "20"


@pytest.mark.parametrize(
    "result",
    [
        lambda: add("0.0", "0.00"),
        lambda: add("-0", "-0.00"),
        lambda: add("-0.5", "0.5"),
        lambda: add("-0", "0"),
        lambda: subtract("1.5", "1.5"),
        lambda: subtract("-0", "0"),
        lambda: subtract("0", "0.0"),
        lambda: subtract("-7", "-7.000"),
        lambda: multiply("-3", "0"),
        lambda: multiply("0.000", "-0.0"),
        lambda: multiply("-0", "-0"),
    ],
)
def test_zero_is_always_the_single_character_zero(result):
    assert result() == "0"


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (lambda: multiply("-0.5", "0.5"), "-0.25"),
        (lambda: subtract("0.5", "1"), "-0.5"),
        (lambda: add("-0.25", "-0.25"), "-0.5"),
        (lambda: subtract("1.25", "1"), "0.25"),
        (lambda: multiply("0.5", "0.5"), "0.25"),
        (lambda: subtract("-1", "-1.001"), "0.001"),
    ],
)
def test_signs_and_values_below_one(result, expected):
    assert result() == expected


def messy(rng):
    number = "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 30)))
    number = "0" * rng.randint(0, 3) + number
    if rng.random() < 0.7:
        number += "." + "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 30)))
        number += "0" * rng.randint(0, 3)
    return ("-" if rng.random() < 0.4 else "") + number


def test_every_result_of_random_messy_inputs_is_canonical():
    rng = random.Random(20260930)
    for _ in range(60):
        a, b = messy(rng), messy(rng)
        for result in (add(a, b), subtract(a, b), multiply(a, b)):
            assert CANONICAL.fullmatch(result), (a, b, result)
            assert result != "-0"
            assert not result.startswith("-0") or result.startswith("-0.")
