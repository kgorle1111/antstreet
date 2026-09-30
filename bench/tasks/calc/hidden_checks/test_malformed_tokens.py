import pytest
from calc import evaluate


@pytest.mark.parametrize("bad", [".5", "5.", "1.2.3", "1..2", "1 + .5", "5. + 1", "(5.)", "."])
def test_invalid_decimal_literals_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize("bad", ["2 ** 3", "2**3", "7 // 2", "7 % 2", "7 ^ 2", "1 & 1", "1 | 1"])
def test_operators_beyond_the_four_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize("bad", ["1e3", "1E3", "1.5e2", "0x10", "0b11", "0o7", "1_000", "1j", "2L"])
def test_python_style_literals_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "abs(1)",
        "pi",
        "e",
        "x + 1",
        "1 + a",
        "max(1, 2)",
        "__import__('os')",
        "1 if 1 else 2",
        "1,5",
    ],
)
def test_names_and_calls_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "١ + ١",
        "１ + １",
        "3 + ٣",
        "१२",
        "2 * ３",
        "1 + 2 = 3",
        "1 + 2;",
        "1 + 2 # note",
        "[1]",
        "{1}",
    ],
)
def test_other_characters_raise(bad):
    with pytest.raises(ValueError):
        evaluate(bad)


@pytest.mark.parametrize("bad", [None, 5, 2.5, b"1 + 1", ["1 + 1"], ("1",), object(), True])
def test_non_string_raises_value_error(bad):
    with pytest.raises(ValueError):
        evaluate(bad)
