import pytest
from duration import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1w1d1h1m1s1ms", 604800 + 86400 + 3600 + 60 + 1 + 0.001),
        ("1s1ms", 1.001),
        ("1m1ms", 60.001),
        ("1w1ms", 604800.001),
        ("1d1m", 86460),
        ("1w1s", 604801),
    ],
)
def test_descending_order_with_units_skipped_is_valid(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize(
    "text",
    [
        "30s1m",
        "1d1w",
        "1h1d",
        "1ms1s",
        "1ms1m",
        "5ms5m",
        "1s 1m",
        "1m 1h",
        "1h30m1d",
        "1m1h1s",
    ],
)
def test_out_of_order_units_are_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize(
    "text",
    [
        "1h1h",
        "1m1m",
        "1s1s",
        "1ms1ms",
        "1w1w",
        "1d 1d",
        "1h30m1h",
        "1h30m30m",
        "1m1s1m",
        "1m1s1s",
        "2s 2s",
    ],
)
def test_repeated_units_are_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)
