import pytest
from calc import evaluate


def test_integer_literals():
    assert evaluate("3") == 3
    assert evaluate("0") == 0
    assert evaluate("42") == 42
    assert evaluate("1234567890") == 1234567890


def test_decimal_literals():
    assert evaluate("2.5") == pytest.approx(2.5)
    assert evaluate("0.25") == pytest.approx(0.25)
    assert evaluate("10.125") == pytest.approx(10.125)
    assert evaluate("0.0") == 0


def test_leading_zeros_are_fine():
    assert evaluate("007") == 7
    assert evaluate("007 + 1") == 8
    assert evaluate("00.5") == pytest.approx(0.5)


def test_decimal_arithmetic_is_float_arithmetic():
    assert evaluate("0.1 + 0.2") == pytest.approx(0.3)
    assert evaluate("1.5 * 4") == pytest.approx(6.0)
    assert evaluate("2.5 - 0.75") == pytest.approx(1.75)


def test_big_integers_are_exact():
    assert evaluate("9007199254740993 + 0") == 9007199254740993
    assert evaluate("12345678901234567890 * 98765432109876543210") == (
        12345678901234567890 * 98765432109876543210
    )
    assert evaluate("99999999999999999999 + 1") == 100000000000000000000


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1+2*3", 7),
        (" 1 + 2 * 3 ", 7),
        ("\t1\t+\t2\t", 3),
        ("1\n+\n2", 3),
        ("1\r\n+\r\n2", 3),
        ("( 1 + 2 ) * 3", 9),
        ("  (  (  4  )  )  ", 4),
        ("- 3", -3),
        ("1 - - 3", 4),
        ("2 * ( - 3 )", -6),
        ("   7   ", 7),
    ],
)
def test_whitespace_between_tokens_is_ignored(text, expected):
    assert evaluate(text) == expected


@pytest.mark.parametrize("bad", ["1 2", "1 2 + 3", "1\t2", "1\n2", "1.5 2", "1 2.5", "(1 2)"])
def test_whitespace_splits_literals(bad):
    with pytest.raises(ValueError):
        evaluate(bad)
