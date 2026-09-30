import pytest
from duration import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("-90s", -90),
        ("-1h30m", -5400),
        ("-250ms", -0.25),
        ("-1.5h", -5400),
        ("-1w", -604800),
        ("-1m5ms", -60.005),
    ],
)
def test_leading_minus_negates_the_value(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


def test_minus_negates_the_whole_duration_not_just_the_first_component():
    assert parse_duration("-2d 4h") == pytest.approx(-187200)
    assert parse_duration("-1h30m") == pytest.approx(-5400)
    assert parse_duration("-1m30s500ms") == pytest.approx(-90.5)


def test_negative_zero_is_zero():
    assert parse_duration("-0s") == 0
    assert parse_duration("-0h0m") == 0


def test_whitespace_around_a_negative_duration():
    assert parse_duration("  -1s") == -1
    assert parse_duration("-1h 30m  ") == pytest.approx(-5400)


@pytest.mark.parametrize(
    "text",
    [
        "-",
        "- ",
        "--1s",
        "- 1s",
        "-\t1s",
        "1h-30m",
        "1h -30m",
        "1s-",
        "+1s",
        "-+1s",
        "1h+30m",
        "-h",
    ],
)
def test_a_sign_anywhere_but_the_very_start_is_rejected(text):
    with pytest.raises(ValueError):
        parse_duration(text)
