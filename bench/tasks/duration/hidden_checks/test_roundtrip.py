import pytest
from duration import format_duration, parse_duration


@pytest.mark.parametrize(
    "seconds",
    [
        0,
        1,
        0.001,
        0.25,
        1.5,
        59.9996,
        90,
        3600,
        12345.678,
        987654.321,
        1e6,
        31536000.123,
        -0.25,
        -90,
        -12345.678,
        0.0004,
    ],
)
def test_parse_of_format_matches_to_the_millisecond(seconds):
    assert round(parse_duration(format_duration(seconds)) * 1000) == round(seconds * 1000)


@pytest.mark.parametrize(
    "text",
    [
        "0s",
        "1ms",
        "250ms",
        "59s999ms",
        "1m",
        "1h30m",
        "1d",
        "1s1ms",
        "10w",
        "1w2d3h4m5s6ms",
        "-1m30s",
        "-250ms",
    ],
)
def test_canonical_strings_survive_a_round_trip(text):
    assert format_duration(parse_duration(text)) == text


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("90s", "1m30s"),
        ("1.5h", "1h30m"),
        ("2d 4h", "2d4h"),
        ("1000ms", "1s"),
        ("60m", "1h"),
        ("25h", "1d1h"),
        ("7d", "1w"),
        ("1.5s", "1s500ms"),
        ("0.5m", "30s"),
        ("-90s", "-1m30s"),
        ("-0s", "0s"),
    ],
)
def test_non_canonical_input_normalises(text, canonical):
    assert format_duration(parse_duration(text)) == canonical
