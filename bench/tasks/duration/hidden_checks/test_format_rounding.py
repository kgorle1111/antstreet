import pytest
from duration import format_duration


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0.001, "1ms"),
        (0.25, "250ms"),
        (0.5, "500ms"),
        (1.5, "1s500ms"),
        (1.001, "1s1ms"),
        (61.25, "1m1s250ms"),
        (12345.678, "3h25m45s678ms"),
        (86400.5, "1d500ms"),
    ],
)
def test_fractions_become_whole_milliseconds(seconds, text):
    assert format_duration(seconds) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0.0006, "1ms"),
        (0.0004, "0s"),
        (1.0004, "1s"),
        (1.0006, "1s1ms"),
        (59.9994, "59s999ms"),
        (0.1234, "123ms"),
        (0.1236, "124ms"),
    ],
)
def test_rounds_to_the_nearest_millisecond(seconds, text):
    assert format_duration(seconds) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0.9996, "1s"),
        (1.9996, "2s"),
        (59.9996, "1m"),
        (119.9996, "2m"),
        (3599.9996, "1h"),
        (86399.9996, "1d"),
        (604799.9996, "1w"),
        (3659.9996, "1h1m"),
    ],
)
def test_rounding_carries_into_the_next_unit(seconds, text):
    assert format_duration(seconds) == text


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (-0.0004, "0s"),
        (-0.0006, "-1ms"),
        (-1.5, "-1s500ms"),
        (-59.9996, "-1m"),
        (-12345.678, "-3h25m45s678ms"),
        (-0.0, "0s"),
    ],
)
def test_negative_fractions(seconds, text):
    assert format_duration(seconds) == text


def test_a_value_that_rounds_to_zero_has_no_sign():
    assert format_duration(0.0004) == "0s"
    assert format_duration(-0.0004) == "0s"
    assert not format_duration(-0.0004).startswith("-")
