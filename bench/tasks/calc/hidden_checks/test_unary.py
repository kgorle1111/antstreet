import pytest
from calc import evaluate


def test_unary_minus_and_plus_on_literals():
    assert evaluate("-3") == -3
    assert evaluate("+3") == 3
    assert evaluate("-2.5") == pytest.approx(-2.5)
    assert evaluate("+2.5") == pytest.approx(2.5)
    assert evaluate("-0") == 0


def test_repeated_unary_operators():
    assert evaluate("--3") == 3
    assert evaluate("---3") == -3
    assert evaluate("++3") == 3
    assert evaluate("+-3") == -3
    assert evaluate("-+3") == -3
    assert evaluate("+-+3") == -3
    assert evaluate("- - 3") == 3
    assert evaluate("-" * 100 + "3") == 3
    assert evaluate("-" * 101 + "3") == -3


def test_unary_on_parenthesised_expressions():
    assert evaluate("-(2 + 3)") == -5
    assert evaluate("-(-(3))") == 3
    assert evaluate("+(2 + 3)") == 5
    assert evaluate("-(1 - 4)") == 3
    assert evaluate("--(2 * 3)") == 6
    assert evaluate("-((1))") == -1


def test_unary_after_a_binary_operator():
    assert evaluate("2 * -3") == -6
    assert evaluate("2 - -3") == 5
    assert evaluate("2 + -3") == -1
    assert evaluate("2 - +3") == -1
    assert evaluate("2--3") == 5
    assert evaluate("2++3") == 5
    assert evaluate("2+-3") == -1
    assert evaluate("2 * - - 3") == 6
    assert evaluate("6 / -4") == pytest.approx(-1.5)
    assert evaluate("6 / - (2 + 1)") == pytest.approx(-2.0)


def test_unary_at_the_start_of_a_larger_expression():
    assert evaluate("-2 + 3") == 1
    assert evaluate("-2 * 3") == -6
    assert evaluate("-2 * -3") == 6
    assert evaluate("-3 - -3") == 0
    assert evaluate("-1 - 2 - 3") == -6
    assert evaluate("(-1) * (-1)") == 1
    assert evaluate("(-2 + 5) * -2") == -6


def test_unary_inside_parentheses_after_operators():
    assert evaluate("1 + (-2)") == -1
    assert evaluate("1 - (-2)") == 3
    assert evaluate("(2 * (-3))") == -6
    assert evaluate("10 / (-2 - 3)") == pytest.approx(-2.0)
