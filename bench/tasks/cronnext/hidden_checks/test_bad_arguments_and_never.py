from datetime import UTC, date, datetime

import pytest
from cronnext import next_fire

AFTER = datetime(2024, 3, 15, 10, 30)


@pytest.mark.parametrize(
    "after",
    [date(2024, 3, 15), "2024-03-15 10:30", None, 1710498600, 1710498600.0, (2024, 3, 15), b"2024"],
)
def test_after_that_is_not_a_datetime_is_a_type_error(after):
    with pytest.raises(TypeError):
        next_fire("* * * * *", after)


@pytest.mark.parametrize(
    "after",
    [
        datetime(2024, 3, 15, 10, 30, tzinfo=UTC),
        datetime(2024, 3, 15, 10, 30, 45, tzinfo=UTC),
    ],
)
def test_after_with_a_time_zone_is_a_value_error(after):
    with pytest.raises(ValueError):
        next_fire("* * * * *", after)


@pytest.mark.parametrize(
    "expr",
    [
        "0 0 31 2 *",
        "0 0 30 2 *",
        "59 23 31 2 *",
        "0 0 31 4 *",
        "0 0 31 6 *",
        "0 0 31 9 *",
        "0 0 31 11 *",
        "0 0 30-31 2 *",
        "*/5 * 31 2 *",
    ],
)
def test_an_expression_that_can_never_fire_is_a_value_error(expr):
    with pytest.raises(ValueError):
        next_fire(expr, AFTER)


def test_a_rare_but_possible_expression_still_fires():
    assert next_fire("0 0 29 2 *", AFTER) == datetime(2028, 2, 29, 0, 0)
    assert next_fire("0 0 31 12 *", AFTER) == datetime(2024, 12, 31, 0, 0)
    assert next_fire("59 23 31 12 *", datetime(2024, 12, 31, 23, 59)) == datetime(
        2025, 12, 31, 23, 59
    )
    # a fire about nine years away is still inside the 3660-day window
    assert next_fire("0 0 29 2 *", datetime(2096, 3, 1, 0, 0)) == datetime(2104, 2, 29, 0, 0)


def test_the_search_window_is_about_ten_years_and_not_one():
    # the next 29 February after 2024-03-01 is more than a year but less than ten years away
    assert next_fire("0 0 29 2 *", datetime(2024, 3, 1, 0, 0)) == datetime(2028, 2, 29, 0, 0)
    assert next_fire("0 0 29 2 *", datetime(2025, 3, 1, 0, 0)) == datetime(2028, 2, 29, 0, 0)


def test_valid_calls_still_work_after_the_errors():
    assert next_fire("30 10 * * *", AFTER) == datetime(2024, 3, 16, 10, 30)
