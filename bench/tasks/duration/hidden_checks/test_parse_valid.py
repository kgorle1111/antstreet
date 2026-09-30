import pytest
from duration import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1w", 604800),
        ("2w", 1209600),
        ("1d", 86400),
        ("1h", 3600),
        ("1m", 60),
        ("45m", 2700),
        ("1s", 1),
        ("90s", 90),
        ("0s", 0),
        ("1ms", 0.001),
        ("250ms", 0.25),
        ("1500ms", 1.5),
        ("007s", 7),
    ],
)
def test_single_component(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1h30m", 5400),
        ("2d 4h", 187200),
        ("1m30s", 90),
        ("1h1s", 3601),
        ("1w5s", 604805),
        ("1s500ms", 1.5),
        ("1w2d3h4m5s6ms", 604800 + 2 * 86400 + 3 * 3600 + 4 * 60 + 5 + 0.006),
        ("1w 2d 3h 4m 5s 6ms", 604800 + 2 * 86400 + 3 * 3600 + 4 * 60 + 5 + 0.006),
    ],
)
def test_several_components_are_added(text, seconds):
    assert parse_duration(text) == pytest.approx(seconds)


def test_ms_is_milliseconds_and_m_is_minutes():
    assert parse_duration("5ms") == pytest.approx(0.005)
    assert parse_duration("5m") == 300
    assert parse_duration("1m5ms") == pytest.approx(60.005)
    assert parse_duration("5m 5ms") == pytest.approx(300.005)
    assert parse_duration("1m1s1ms") == pytest.approx(61.001)


@pytest.mark.parametrize("text", ["1h  30m", "1h\t30m", "1h \t 30m", "1h\n30m"])
def test_any_whitespace_between_components(text):
    assert parse_duration(text) == 5400


@pytest.mark.parametrize("text", ["  1h30m", "1h30m  ", "\t1h30m\n", "  1h 30m  "])
def test_whitespace_around_the_whole_string(text):
    assert parse_duration(text) == 5400


def test_result_is_a_float():
    assert isinstance(parse_duration("90s"), float)
    assert isinstance(parse_duration("1h"), float)
    assert isinstance(parse_duration("0s"), float)
