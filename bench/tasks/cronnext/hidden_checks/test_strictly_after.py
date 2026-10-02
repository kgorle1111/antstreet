from datetime import datetime

import pytest
from cronnext import next_fire


def test_a_match_at_exactly_after_is_not_returned():
    after = datetime(2024, 3, 15, 10, 30)
    assert next_fire("30 10 * * *", after) == datetime(2024, 3, 16, 10, 30)
    assert next_fire("* * * * *", after) == datetime(2024, 3, 15, 10, 31)
    assert next_fire("30 * * * *", after) == datetime(2024, 3, 15, 11, 30)
    assert next_fire("0 0 15 3 *", datetime(2024, 3, 15, 0, 0)) == datetime(2025, 3, 15, 0, 0)


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2024, 3, 15, 10, 30, 1), datetime(2024, 3, 16, 10, 30)),
        (datetime(2024, 3, 15, 10, 30, 45), datetime(2024, 3, 16, 10, 30)),
        (datetime(2024, 3, 15, 10, 30, 0, 1), datetime(2024, 3, 16, 10, 30)),
        (datetime(2024, 3, 15, 10, 29, 59), datetime(2024, 3, 15, 10, 30)),
        (datetime(2024, 3, 15, 10, 29, 59, 999999), datetime(2024, 3, 15, 10, 30)),
        (datetime(2024, 3, 15, 10, 29, 0), datetime(2024, 3, 15, 10, 30)),
        (datetime(2024, 3, 15, 10, 29, 30), datetime(2024, 3, 15, 10, 30)),
    ],
)
def test_only_the_minute_of_after_counts(after, expected):
    assert next_fire("30 10 * * *", after) == expected


def test_seconds_in_after_do_not_leak_into_the_result():
    after = datetime(2024, 3, 15, 10, 30, 45, 123456)
    assert next_fire("* * * * *", after) == datetime(2024, 3, 15, 10, 31)
    assert next_fire("*/5 * * * *", after) == datetime(2024, 3, 15, 10, 35)
    assert next_fire("0 11 * * *", after) == datetime(2024, 3, 15, 11, 0)


def test_the_result_is_always_later_than_after():
    after = datetime(2024, 3, 15, 10, 30)
    for expr in ("* * * * *", "30 10 * * *", "0 0 1 * *", "*/10 * * * *", "0 0 * * 5"):
        for offset_seconds in (0, 1, 30, 59):
            start = after.replace(second=offset_seconds)
            assert next_fire(expr, start) > start
