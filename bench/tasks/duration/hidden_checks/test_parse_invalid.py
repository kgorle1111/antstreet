import pytest
from duration import parse_duration


@pytest.mark.parametrize("text", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_empty_or_whitespace_only_is_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("text", ["30", "1h30", "1h 30", "1.5", "0", "1m30", "30 s"])
def test_a_number_without_a_unit_is_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("text", ["h", "s", "ms", "h30m", "1h m", "1hm", "s5"])
def test_a_unit_without_a_number_is_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    ["1x", "1hr", "1hh", "1min", "1mins", "1sec", "1H", "1M", "1S", "1W", "1D", "1MS", "1Ms", "1y"],
)
def test_unknown_or_uppercase_units_are_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("text", ["1 h", "5 ms", "1h 30 m", "1\tm", "1.5 s"])
def test_whitespace_between_a_number_and_its_unit_is_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    [
        "abc",
        "1h30m garbage",
        "garbage 1h",
        "1h,30m",
        "1h&30m",
        "1h30m!",
        "(1h)",
        "1h\x0030m",
        "1h;",
    ],
)
def test_other_characters_are_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("value", [90, 0, 1.5, None, b"1h", ["1h"], ("1h",), {"1h"}])
def test_non_string_input_raises_value_error(value):
    with pytest.raises(ValueError):
        parse_duration(value)


def test_valid_strings_still_parse_after_the_errors():
    assert parse_duration("1h") == 3600
    assert parse_duration("1m") == 60
