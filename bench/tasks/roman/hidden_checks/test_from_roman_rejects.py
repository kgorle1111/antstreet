import pytest
from roman import from_roman


@pytest.mark.parametrize("bad", ["IIII", "VV", "XXXX", "LL", "DD", "CCCC", "VIIII", "IXX"])
def test_repeated_symbols_beyond_the_rule(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", ["IC", "IL", "XM", "XD", "VX", "LC", "DM", "IM", "VL"])
def test_illegal_subtractive_pairs(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", ["IIX", "IIV", "XXC", "VIV", "IXI", "XCX", "CMC", "IVI"])
def test_wrong_order_or_double_subtraction(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", ["MMMM", "MMMMCMXCIX", "MMMMM"])
def test_above_3999(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", ["iv", "Iv", "mcmxciv", "xiv", "MCMxciv"])
def test_lowercase_and_mixed_case(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", ["", " ", " X", "X ", "\nX", "X\n", "X I", "IV\t"])
def test_empty_and_whitespace(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", ["ABC", "X1", "12", "XIV!", "IV-V", "Ⅹ"])
def test_other_characters(bad):
    with pytest.raises(ValueError):
        from_roman(bad)


@pytest.mark.parametrize("bad", [None, 5, 4.0, b"X", ["X"]])
def test_non_strings(bad):
    with pytest.raises(ValueError):
        from_roman(bad)
