from datetime import datetime

import pytest
from cronnext import next_fire, next_fires


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        ("* * * * *", datetime(2024, 12, 31, 23, 59), datetime(2025, 1, 1, 0, 0)),
        ("* * * * *", datetime(2024, 2, 28, 23, 59), datetime(2024, 2, 29, 0, 0)),
        ("* * * * *", datetime(2023, 2, 28, 23, 59), datetime(2023, 3, 1, 0, 0)),
        ("* * * * *", datetime(2024, 2, 29, 23, 59), datetime(2024, 3, 1, 0, 0)),
        ("* * * * *", datetime(2024, 4, 30, 23, 59, 30), datetime(2024, 5, 1, 0, 0)),
        ("0 0 * * *", datetime(2024, 3, 31, 23, 30), datetime(2024, 4, 1, 0, 0)),
        ("5 * * * *", datetime(2024, 3, 15, 23, 30), datetime(2024, 3, 16, 0, 5)),
        ("59 23 31 12 *", datetime(2024, 12, 31, 23, 59), datetime(2025, 12, 31, 23, 59)),
        ("0 0 1 1 *", datetime(2024, 12, 31, 23, 59), datetime(2025, 1, 1, 0, 0)),
        ("30 6 * * *", datetime(1999, 12, 31, 12, 0), datetime(2000, 1, 1, 6, 30)),
    ],
)
def test_rollovers_of_the_minute_hour_day_month_and_year(expr, after, expected):
    assert next_fire(expr, after) == expected


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        ("0 0 31 * *", datetime(2024, 4, 15, 0, 0), datetime(2024, 5, 31, 0, 0)),
        ("0 0 31 * *", datetime(2024, 1, 31, 0, 0), datetime(2024, 3, 31, 0, 0)),
        ("0 0 31 * *", datetime(2024, 7, 31, 0, 0), datetime(2024, 8, 31, 0, 0)),
        ("0 0 31 * *", datetime(2024, 8, 31, 0, 0), datetime(2024, 10, 31, 0, 0)),
        ("0 0 30 * *", datetime(2024, 1, 31, 0, 0), datetime(2024, 3, 30, 0, 0)),
        ("0 0 29 * *", datetime(2023, 1, 30, 0, 0), datetime(2023, 3, 29, 0, 0)),
        ("0 0 29 * *", datetime(2024, 1, 30, 0, 0), datetime(2024, 2, 29, 0, 0)),
        ("0 0 31 4,6,9,11 *", datetime(2024, 1, 1, 0, 0), None),
    ],
)
def test_a_day_a_month_does_not_have_is_skipped(expr, after, expected):
    if expected is None:
        with pytest.raises(ValueError):
            next_fire(expr, after)
    else:
        assert next_fire(expr, after) == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2024, 3, 1, 0, 0), datetime(2028, 2, 29, 0, 0)),
        (datetime(2024, 2, 29, 0, 0), datetime(2028, 2, 29, 0, 0)),
        (datetime(2024, 2, 28, 12, 0), datetime(2024, 2, 29, 0, 0)),
        (datetime(2023, 3, 1, 0, 0), datetime(2024, 2, 29, 0, 0)),
        (datetime(2096, 3, 1, 0, 0), datetime(2104, 2, 29, 0, 0)),  # 2100 is not a leap year
        (datetime(1896, 3, 1, 0, 0), datetime(1904, 2, 29, 0, 0)),  # nor is 1900
        (datetime(1999, 3, 1, 0, 0), datetime(2000, 2, 29, 0, 0)),  # 2000 is
    ],
)
def test_the_29th_of_february_follows_the_gregorian_leap_rule(after, expected):
    assert next_fire("0 0 29 2 *", after) == expected


def test_leap_days_in_a_row():
    assert next_fires("30 12 29 2 *", datetime(2024, 3, 1, 0, 0), 3) == [
        datetime(2028, 2, 29, 12, 30),
        datetime(2032, 2, 29, 12, 30),
        datetime(2036, 2, 29, 12, 30),
    ]


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2024, 3, 15, 10, 30), datetime(2024, 3, 16, 0, 0)),
        (datetime(2024, 3, 31, 0, 0), datetime(2024, 4, 1, 0, 0)),
        (datetime(2024, 12, 31, 0, 0), datetime(2025, 1, 1, 0, 0)),
    ],
)
def test_midnight_rolls_to_the_next_day(after, expected):
    assert next_fire("0 0 * * *", after) == expected


def test_a_whole_year_of_first_of_the_month_fires():
    fires = next_fires("0 0 1 * *", datetime(2023, 12, 31, 12, 0), 12)
    assert fires == [datetime(2024, month, 1, 0, 0) for month in range(1, 13)]


def test_every_month_end_for_a_year():
    fires = next_fires("0 0 31 * *", datetime(2024, 1, 1, 0, 0), 7)
    assert [(f.month, f.day) for f in fires] == [
        (1, 31),
        (3, 31),
        (5, 31),
        (7, 31),
        (8, 31),
        (10, 31),
        (12, 31),
    ]
