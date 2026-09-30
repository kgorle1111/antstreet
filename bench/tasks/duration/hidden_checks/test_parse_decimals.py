import pytest
from duration import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1.5h", 5400),
        ("0.5s", 0.5),
        ("2.25m", 135),
        ("10.0s", 10),
        ("1.5ms", 0.0015),
        ("0.5d", 43200),
        ("1.5w", 907200),
        ("0.1s", 0.1),
        ("0.75h", 2700),
    ],
)
def test_decimal_numbers(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1.5h30m", 7200),
        ("1.5d 2.5h", 138600),
        ("2.5m 1.5s", 151.5),
        ("1h0.5s", 3600.5),
    ],
)
def test_any_component_may_be_decimal(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize(
    "text",
    [
        ".5s",
        "1.s",
        "1.5.5s",
        "1..5s",
        "1.5.s",
        "1,5s",
        "1e3s",
        "1E3s",
        "1_0s",
        "0x10s",
        "1h .5m",
        "1h.5m",
    ],
)
def test_malformed_numbers_are_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)


@pytest.mark.parametrize("text", ["٣s", "١٢s", "1٢m", "１s", "1.٥s"])
def test_non_ascii_digits_are_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)
