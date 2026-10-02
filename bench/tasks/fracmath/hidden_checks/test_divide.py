import pytest
from fracmath import divide


@pytest.mark.parametrize(
    ("a", "b", "quotient"),
    [
        ("1/2", "1/4", "2"),
        ("3", "2", "1 1/2"),
        ("-1 1/2", "3/4", "-2"),
        ("1", "3", "1/3"),
        ("3/4", "3/4", "1"),
        ("1/2", "2", "1/4"),
        ("2", "1/2", "4"),
        ("0", "5", "0"),
        ("0", "-3/4", "0"),
        ("7", "2", "3 1/2"),
        ("1 1/2", "1/2", "3"),
        ("1/3", "1/6", "2"),
        ("5", "1", "5"),
        ("10", "4", "2 1/2"),
        ("2/3", "3/4", "8/9"),
        ("3/2", "9/4", "2/3"),
        ("6", "4", "1 1/2"),
    ],
)
def test_quotients(a, b, quotient):
    assert divide(a, b) == quotient


@pytest.mark.parametrize(
    ("a", "b", "quotient"),
    [
        ("-1/2", "1/4", "-2"),
        ("1/2", "-1/4", "-2"),
        ("-1/2", "-1/4", "2"),
        ("1/3", "-2/3", "-1/2"),
        ("-3", "2", "-1 1/2"),
        ("3", "-2", "-1 1/2"),
        ("-3", "-2", "1 1/2"),
        ("-1 1/2", "-3/4", "2"),
        ("-7", "2", "-3 1/2"),
        ("1", "-3", "-1/3"),
        ("-1", "3", "-1/3"),
    ],
)
def test_signs(a, b, quotient):
    assert divide(a, b) == quotient


@pytest.mark.parametrize("b", ["0", "0/5", "-0", "0 0/3", "00"])
def test_dividing_by_zero_is_a_value_error_not_zero_division(b):
    with pytest.raises(ValueError) as info:
        divide("1/2", b)
    assert not isinstance(info.value, ZeroDivisionError)


def test_zero_divided_by_zero_is_a_value_error():
    with pytest.raises(ValueError):
        divide("0", "0")


def test_the_arithmetic_is_exact():
    assert divide("1", "3") == "1/3"
    assert divide("1000000000000000000000", "3") == "333333333333333333333 1/3"
    assert divide("1/100000000000000000000", "1/10000000000000000000") == "1/10"
    assert divide("123456789012345678901234567890", "123456789012345678901234567890") == "1"


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
        divide(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [(None, "1/2"), ("1/2", None), (1, "1/2"), ("1/2", 0.5), (b"1/2", "1/2"), ("1/2", ["1/2"])],
)
def test_arguments_that_are_not_strings_are_type_errors(a, b):
    with pytest.raises(TypeError):
        divide(a, b)


def test_the_result_is_a_str():
    assert isinstance(divide("1/2", "1/3"), str)
