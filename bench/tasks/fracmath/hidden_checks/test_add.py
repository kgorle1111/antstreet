import pytest
from fracmath import add


@pytest.mark.parametrize(
    ("a", "b", "total"),
    [
        ("1/2", "1/3", "5/6"),
        ("1/2", "1/2", "1"),
        ("3/4", "3/4", "1 1/2"),
        ("-1 1/2", "1/2", "-1"),
        ("1/4", "1/4", "1/2"),
        ("1/3", "1/6", "1/2"),
        ("2/3", "2/3", "1 1/3"),
        ("1 1/2", "2 3/4", "4 1/4"),
        ("0", "0", "0"),
        ("0", "3/4", "3/4"),
        ("5", "7", "12"),
        ("1/2", "-1/2", "0"),
        ("-1/2", "-1/3", "-5/6"),
        ("-3/4", "1/4", "-1/2"),
        ("-1 1/2", "-2 3/4", "-4 1/4"),
        ("1/2", "-3/4", "-1/4"),
        ("-1/2", "3/4", "1/4"),
        ("-2", "1/2", "-1 1/2"),
        ("6/4", "10/4", "4"),
        ("1/6", "1/10", "4/15"),
        ("7/8", "7/8", "1 3/4"),
    ],
)
def test_sums(a, b, total):
    assert add(a, b) == total
    assert add(b, a) == total


def test_a_zero_sum_has_no_sign():
    assert add("1/2", "-1/2") == "0"
    assert add("-3", "3") == "0"
    assert add("-1 1/2", "1 1/2") == "0"
    assert add("-0", "0") == "0"


def test_a_negative_mixed_number_is_one_negative_value():
    # -1 1/2 + 1/2 is -3/2 + 1/2 = -1, but -1 + 1/2 + 1/2 would be 0
    assert add("-1 1/2", "1/2") == "-1"
    assert add("-1 1/2", "1 1/2") == "0"
    assert add("-2 1/2", "1/2") == "-2"
    assert add("-1 1/4", "-1 1/4") == "-2 1/2"


@pytest.mark.parametrize(
    ("a", "b", "total"),
    [
        ("1/10", "2/10", "3/10"),
        ("1/3", "1/3", "2/3"),
        ("999999999999999999/1", "1/1", "1000000000000000000"),
        ("1/3", "123456789012345678901234567890", "123456789012345678901234567890 1/3"),
        ("1/100000000000000000000", "1/100000000000000000000", "1/50000000000000000000"),
        ("99999999999999999999/100000000000000000000", "1/100000000000000000000", "1"),
    ],
)
def test_the_arithmetic_is_exact(a, b, total):
    assert add(a, b) == total


@pytest.mark.parametrize(
    "a",
    ["  1/2", "1 1/2  ", "\t1/2\n", "01/02", "1  1/2"],
)
def test_the_inputs_follow_the_parsing_rules(a):
    assert add(a, "0") in {"1/2", "1 1/2"}


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("1/0", "1/2"),
        ("1/2", "1/0"),
        ("", "1/2"),
        ("1/2", ""),
        ("1.5", "1"),
        ("1 2/2", "1"),
        ("x", "y"),
    ],
)
def test_text_that_does_not_parse_is_a_value_error(a, b):
    with pytest.raises(ValueError):
        add(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [(None, "1/2"), ("1/2", None), (1, "1/2"), ("1/2", 0.5), (b"1/2", "1/2"), ("1/2", ["1/2"])],
)
def test_arguments_that_are_not_strings_are_type_errors(a, b):
    with pytest.raises(TypeError):
        add(a, b)


def test_the_result_is_a_str():
    assert isinstance(add("1/2", "1/3"), str)
