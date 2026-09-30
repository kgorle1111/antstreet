import pytest
from calc import evaluate


@pytest.mark.parametrize(
    "text",
    [
        "1 / 0",
        "1 / 0.0",
        "0 / 0",
        "0.0 / 0",
        "-5 / 0",
        "1 / (2 - 2)",
        "1 / (0.5 - 0.5)",
        "3 / (1 - 1.0)",
        "1 / 0 / 2",
        "2 * 3 / 0",
        "1 + 2 / 0",
        "(1 + 1) / (3 - 3)",
        "1 / -0",
        "1 / (0 * 5)",
        "  1  /  0  ",
    ],
)
def test_zero_divisor_raises_zero_division_error(text):
    with pytest.raises(ZeroDivisionError):
        evaluate(text)


@pytest.mark.parametrize("text", ["0 * (1 / 0)", "(1 / 0) * 0", "0 + 0 * (5 / (1 - 1))"])
def test_no_short_circuit_around_a_zero_division(text):
    with pytest.raises(ZeroDivisionError):
        evaluate(text)


def test_zero_dividend_is_fine():
    assert evaluate("0 / 5") == 0
    assert evaluate("0 / -5") == 0
    assert evaluate("0.0 / 3") == 0


def test_nonzero_small_divisor_is_fine():
    assert evaluate("1 / 0.5") == pytest.approx(2.0)
    assert evaluate("1 / 0.001") == pytest.approx(1000.0)
