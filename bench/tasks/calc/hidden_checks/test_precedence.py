import pytest
from calc import evaluate


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2 + 3 * 4", 14),
        ("3 * 4 + 2", 14),
        ("2 * 3 + 4 * 5", 26),
        ("10 - 2 * 3", 4),
        ("2 + 6 / 3", 4.0),
        ("6 / 3 + 2", 4.0),
        ("1 + 2 * 3 - 4 / 2", 5.0),
        ("2 * 3 * 4 + 1", 25),
    ],
)
def test_multiplicative_binds_tighter_than_additive(text, expected):
    assert evaluate(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("(2 + 3) * 4", 20),
        ("2 * (3 + 4)", 14),
        ("(1 + 2) * (3 + 4)", 21),
        ("10 - (2 + 3)", 5),
        ("10 - (2 - 3)", 11),
        ("12 / (2 + 2)", 3.0),
        ("(2)", 2),
        ("((2))", 2),
        ("(((1 + 2) * 3) - 4) * 5", 25),
        ("2 * (3 + (4 - 1) * 2)", 18),
    ],
)
def test_parentheses_override_precedence(text, expected):
    assert evaluate(text) == pytest.approx(expected)


def test_deeply_nested_parentheses():
    assert evaluate("(" * 50 + "1" + ")" * 50) == 1
    assert evaluate("(" * 40 + "1 + " + "(2 * 3)" + ")" * 40) == 7


def test_parenthesised_value_can_be_an_operand_anywhere():
    assert evaluate("(1) + (2)") == 3
    assert evaluate("(1) - (2) * (3) / (4)") == pytest.approx(-0.5)
