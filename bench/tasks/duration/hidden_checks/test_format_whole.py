import pytest
from duration import format_duration


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (1, "1s"),
        (59, "59s"),
        (60, "1m"),
        (90, "1m30s"),
        (3599, "59m59s"),
        (3600, "1h"),
        (3601, "1h1s"),
        (3660, "1h1m"),
        (3661, "1h1m1s"),
        (5400, "1h30m"),
        (86399, "23h59m59s"),
        (86400, "1d"),
        (86401, "1d1s"),
        (187200, "2d4h"),
        (604799, "6d23h59m59s"),
        (604800, "1w"),
        (6048000, "10w"),
        (1_000_000, "1w4d13h46m40s"),
    ],
)
def test_whole_seconds(seconds, text):
    assert format_duration(seconds) == text


@pytest.mark.parametrize(("seconds", "text"), [(90.0, "1m30s"), (3600.0, "1h"), (86400.0, "1d")])
def test_whole_floats_format_like_ints(seconds, text):
    assert format_duration(seconds) == text


@pytest.mark.parametrize("seconds", [0, 0.0])
def test_zero_is_zero_seconds(seconds):
    assert format_duration(seconds) == "0s"


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(-1, "-1s"), (-90, "-1m30s"), (-3600, "-1h"), (-604800, "-1w"), (-90.0, "-1m30s")],
)
def test_negative_values_get_a_leading_minus(seconds, text):
    assert format_duration(seconds) == text


def test_zero_components_are_omitted_and_there_are_no_separators():
    assert format_duration(86400 + 1) == "1d1s"
    assert format_duration(604800 + 60) == "1w1m"
    assert " " not in format_duration(1_000_000)


def test_result_is_a_str():
    assert isinstance(format_duration(90), str)
    assert isinstance(format_duration(0), str)
