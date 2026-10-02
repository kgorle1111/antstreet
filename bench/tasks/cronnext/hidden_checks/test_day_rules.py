from datetime import datetime

import pytest
from cronnext import next_fire, next_fires

AFTER = datetime(2024, 3, 15, 10, 30)  # a Friday


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("0 0 * * 0", datetime(2024, 3, 17, 0, 0)),  # Sunday
        ("0 0 * * 1", datetime(2024, 3, 18, 0, 0)),  # Monday
        ("0 0 * * 2", datetime(2024, 3, 19, 0, 0)),
        ("0 0 * * 3", datetime(2024, 3, 20, 0, 0)),
        ("0 0 * * 4", datetime(2024, 3, 21, 0, 0)),
        ("0 0 * * 5", datetime(2024, 3, 22, 0, 0)),  # next Friday: today's 00:00 has passed
        ("0 12 * * 5", datetime(2024, 3, 15, 12, 0)),  # Friday, still ahead today
        ("0 0 * * 6", datetime(2024, 3, 16, 0, 0)),  # Saturday
        ("0 0 * * 1-5", datetime(2024, 3, 18, 0, 0)),  # weekdays
        ("0 0 * * 0,6", datetime(2024, 3, 16, 0, 0)),  # weekend
        ("30 8 * * 1-5", datetime(2024, 3, 18, 8, 30)),
    ],
)
def test_day_of_week_numbering_starts_with_sunday_as_zero(expr, expected):
    assert next_fire(expr, AFTER) == expected


def test_sunday_is_0_and_saturday_is_6_over_a_whole_week():
    sunday = datetime(2024, 3, 17, 0, 0)
    days = {0: 24, 1: 18, 2: 19, 3: 20, 4: 21, 5: 22, 6: 23}
    for number, day in days.items():
        assert next_fire(f"0 0 * * {number}", sunday) == datetime(2024, 3, day, 0, 0)
    assert next_fire("0 0 * * 0", datetime(2024, 3, 16, 12, 0)) == datetime(2024, 3, 17, 0, 0)
    assert next_fire("0 0 * * 6", datetime(2024, 3, 17, 12, 0)) == datetime(2024, 3, 23, 0, 0)


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        # the 13th or a Friday: the Friday comes first
        ("0 0 13 * 5", AFTER, datetime(2024, 3, 22, 0, 0)),
        # the 1st or a Monday: Monday 18 March comes before 1 April
        ("0 0 1 * 1", AFTER, datetime(2024, 3, 18, 0, 0)),
        # the 16th or a Sunday: Saturday the 16th comes first
        ("0 0 16 * 0", AFTER, datetime(2024, 3, 16, 0, 0)),
        # the 20th or a Saturday: Saturday the 16th
        ("0 0 20 * 6", AFTER, datetime(2024, 3, 16, 0, 0)),
        # the 17th or a Wednesday: Sunday the 17th is the 17th
        ("0 0 17 * 3", AFTER, datetime(2024, 3, 17, 0, 0)),
        # April only: Monday 1 April comes before Friday the 5th
        ("0 0 5 4 1", AFTER, datetime(2024, 4, 1, 0, 0)),
    ],
)
def test_when_both_day_fields_are_restricted_either_one_matches(expr, after, expected):
    assert next_fire(expr, after) == expected


def test_both_restricted_is_the_union_not_the_intersection():
    fires = next_fires("0 0 1,15 * 1", datetime(2024, 4, 29, 12, 0), 6)
    # every Monday plus the 1st and the 15th
    assert fires == [
        datetime(2024, 5, 1, 0, 0),
        datetime(2024, 5, 6, 0, 0),
        datetime(2024, 5, 13, 0, 0),
        datetime(2024, 5, 15, 0, 0),
        datetime(2024, 5, 20, 0, 0),
        datetime(2024, 5, 27, 0, 0),
    ]


def test_with_a_star_in_one_day_field_only_the_other_one_is_used():
    assert next_fire("0 0 15 * *", datetime(2024, 3, 1, 0, 0)) == datetime(2024, 3, 15, 0, 0)
    assert next_fire("0 0 * * 1", datetime(2024, 3, 1, 0, 0)) == datetime(2024, 3, 4, 0, 0)
    # a restricted day-of-month with * for the weekday is not widened to every Friday
    fires = next_fires("0 0 10,20 * *", datetime(2024, 3, 1, 0, 0), 4)
    assert [f.day for f in fires] == [10, 20, 10, 20]


def test_both_day_fields_star_is_every_day():
    fires = next_fires("30 6 * * *", datetime(2024, 3, 15, 10, 30), 3)
    assert fires == [datetime(2024, 3, d, 6, 30) for d in (16, 17, 18)]


def test_the_month_field_still_has_to_match_with_both_day_fields_set():
    # the 13th or a Friday, but only in April
    assert next_fire("0 0 13 4 5", AFTER) == datetime(2024, 4, 5, 0, 0)
    assert next_fire("0 0 13 4 5", datetime(2024, 4, 5, 0, 0)) == datetime(2024, 4, 12, 0, 0)
    assert next_fire("0 0 13 4 5", datetime(2024, 4, 26, 0, 0)) == datetime(2025, 4, 4, 0, 0)


def test_a_day_of_month_that_never_exists_leaves_the_weekday_half_working():
    # 31 February never exists, so only the Mondays of February fire
    assert next_fire("0 0 31 2 1", AFTER) == datetime(2025, 2, 3, 0, 0)
    assert next_fire("0 0 31 2 1", datetime(2025, 2, 3, 0, 0)) == datetime(2025, 2, 10, 0, 0)
    assert next_fire("0 0 31 2 1", datetime(2025, 2, 24, 0, 0)) == datetime(2026, 2, 2, 0, 0)
