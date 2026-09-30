import pytest
from calc import evaluate


@pytest.mark.parametrize(
    "text, expected",
    [
        ("3", 3),
        ("0", 0),
        ("1 + 2", 3),
        ("7 - 7", 0),
        ("2 * 3", 6),
        ("1 + 2 * 3", 7),
        ("(1 + 2) * 3", 9),
        ("-4", -4),
        ("--4", 4),
        ("2 * -3", -6),
        ("10 - 2 - 3", 5),
        ("12345678901234567890 + 1", 12345678901234567891),
    ],
)
def test_integer_only_expressions_give_int(text, expected):
    result = evaluate(text)
    assert type(result) is int
    assert result == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2.5", 2.5),
        ("2.0", 2.0),
        ("0.0", 0.0),
        ("1 + 2.0", 3.0),
        ("2.0 + 1", 3.0),
        ("1.5 + 1.5", 3.0),
        ("2 * 1.5", 3.0),
        ("-2.5", -2.5),
        ("(1 + 2) * 1.0", 3.0),
        ("0 * 1.5", 0.0),
        ("5 - 5.0", 0.0),
        ("1 + (2 * 3.0)", 7.0),
    ],
)
def test_any_decimal_literal_gives_float(text, expected):
    result = evaluate(text)
    assert type(result) is float
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("4 / 2", 2.0),
        ("1 / 1", 1.0),
        ("0 / 5", 0.0),
        ("6 / 3 * 2", 4.0),
        ("1 + 4 / 2", 3.0),
        ("(8 / 4) + 1", 3.0),
        ("-4 / 2", -2.0),
        ("2 * (6 / 3)", 4.0),
        ("7 / 2", 3.5),
        ("1 / 3", 1 / 3),
    ],
)
def test_any_division_gives_float_even_when_exact(text, expected):
    result = evaluate(text)
    assert type(result) is float
    assert result == pytest.approx(expected)


def test_division_is_true_division_not_floor_division():
    assert evaluate("7 / 2") == pytest.approx(3.5)
    assert evaluate("-7 / 2") == pytest.approx(-3.5)
    assert evaluate("1 / 4") == pytest.approx(0.25)
