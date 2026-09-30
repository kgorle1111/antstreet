import pytest
from semver import parse


@pytest.mark.parametrize(
    "bad",
    [
        " 1.2.3",
        "1.2.3 ",
        " 1.2.3 ",
        "1.2.3\n",
        "\n1.2.3",
        "\t1.2.3",
        "1.2.3\r\n",
        "1. 2.3",
        "1.2.3-a b",
        "1.2.3+a b",
    ],
)
def test_whitespace_raises(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "1.2.3-a_b",
        "1.2.3+a_b",
        "1.2.3-a!",
        "1.2.3-a/b",
        "1.2.3-a:b",
        "1.2.3-é",
        "1.2.3+é",
        "1.2.3-α",
        "1.2.3#1",
        "1.2.3~1",
        "1,2,3",
        "1.2.3-a,b",
    ],
)
def test_illegal_characters_raise(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize(
    "bad",
    [
        "١.٢.٣",  # Arabic-Indic digits
        "1.2.३",  # Devanagari digit
        "１.２.３",  # fullwidth digits
        "1.2.3-٣",
        "1.2.3+٣",
    ],
)
def test_non_ascii_digits_raise(bad):
    with pytest.raises(ValueError):
        parse(bad)


@pytest.mark.parametrize("bad", [None, 123, 1.2, b"1.2.3", ["1.2.3"], ("1", "2", "3"), object()])
def test_non_string_raises_value_error(bad):
    with pytest.raises(ValueError):
        parse(bad)
