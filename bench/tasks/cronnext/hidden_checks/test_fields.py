from datetime import datetime

import pytest
from cronnext import next_fire, next_fires

AFTER = datetime(2024, 3, 15, 10, 30)  # a Friday


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        ("0 9-17 * * *", datetime(2024, 3, 15, 8, 0), datetime(2024, 3, 15, 9, 0)),
        ("0 9-17 * * *", datetime(2024, 3, 15, 9, 0), datetime(2024, 3, 15, 10, 0)),
        ("0 9-17 * * *", datetime(2024, 3, 15, 17, 0), datetime(2024, 3, 16, 9, 0)),
        ("0 9-17 * * *", datetime(2024, 3, 15, 16, 30), datetime(2024, 3, 15, 17, 0)),
        ("5-10,20-25 * * * *", datetime(2024, 3, 15, 10, 10), datetime(2024, 3, 15, 10, 20)),
        ("5-10,20-25 * * * *", datetime(2024, 3, 15, 10, 25), datetime(2024, 3, 15, 11, 5)),
        ("0 8-8 * * *", datetime(2024, 3, 15, 8, 0), datetime(2024, 3, 16, 8, 0)),
    ],
)
def test_ranges_include_both_ends(expr, after, expected):
    assert next_fire(expr, after) == expected


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        ("0,30 * * * *", datetime(2024, 3, 15, 10, 30), datetime(2024, 3, 15, 11, 0)),
        ("0,30 * * * *", datetime(2024, 3, 15, 10, 10), datetime(2024, 3, 15, 10, 30)),
        ("0 8,12,18 * * *", datetime(2024, 3, 15, 12, 0), datetime(2024, 3, 15, 18, 0)),
        ("0 8,12,18 * * *", datetime(2024, 3, 15, 18, 0), datetime(2024, 3, 16, 8, 0)),
        ("30,0,15 * * * *", datetime(2024, 3, 15, 10, 5), datetime(2024, 3, 15, 10, 15)),
        ("0 0 1,15 * *", datetime(2024, 3, 2, 0, 0), datetime(2024, 3, 15, 0, 0)),
        ("0 0 1 1,7 *", datetime(2024, 3, 2, 0, 0), datetime(2024, 7, 1, 0, 0)),
        ("1,1,1 * * * *", datetime(2024, 3, 15, 10, 0), datetime(2024, 3, 15, 10, 1)),
    ],
)
def test_lists(expr, after, expected):
    assert next_fire(expr, after) == expected


@pytest.mark.parametrize(
    ("expr", "after", "expected"),
    [
        ("*/15 * * * *", datetime(2024, 3, 15, 10, 45), datetime(2024, 3, 15, 11, 0)),
        ("*/20 * * * *", datetime(2024, 3, 15, 10, 45), datetime(2024, 3, 15, 11, 0)),
        ("*/20 * * * *", datetime(2024, 3, 15, 10, 20), datetime(2024, 3, 15, 10, 40)),
        ("*/60 * * * *", datetime(2024, 3, 15, 10, 30), datetime(2024, 3, 15, 11, 0)),
        ("10-20/5 * * * *", datetime(2024, 3, 15, 10, 12), datetime(2024, 3, 15, 10, 15)),
        ("10-20/5 * * * *", datetime(2024, 3, 15, 10, 20), datetime(2024, 3, 15, 11, 10)),
        ("11-30/10 * * * *", datetime(2024, 3, 15, 10, 12), datetime(2024, 3, 15, 10, 21)),
        ("0 */6 * * *", datetime(2024, 3, 15, 10, 30), datetime(2024, 3, 15, 12, 0)),
        ("0 */6 * * *", datetime(2024, 3, 15, 18, 0), datetime(2024, 3, 16, 0, 0)),
        ("0 3-20/8 * * *", datetime(2024, 3, 15, 4, 0), datetime(2024, 3, 15, 11, 0)),
        ("0,30-40/5 * * * *", datetime(2024, 3, 15, 10, 1), datetime(2024, 3, 15, 10, 30)),
    ],
)
def test_steps_count_from_the_start_of_the_item(expr, after, expected):
    assert next_fire(expr, after) == expected


def test_a_step_on_day_of_month_starts_at_the_first_not_at_zero():
    # */10 on day of month is 1, 11, 21 and 31, not 10, 20 and 30
    assert next_fire("0 0 */10 * *", datetime(2024, 3, 15, 10, 30)) == datetime(2024, 3, 21, 0, 0)
    assert next_fire("0 0 */10 * *", datetime(2024, 3, 11, 0, 0)) == datetime(2024, 3, 21, 0, 0)
    assert next_fire("0 0 */10 * *", datetime(2024, 3, 21, 0, 0)) == datetime(2024, 3, 31, 0, 0)
    assert next_fire("0 0 */10 * *", datetime(2024, 3, 31, 0, 0)) == datetime(2024, 4, 1, 0, 0)
    assert next_fire("0 0 */10 * *", datetime(2024, 3, 1, 0, 0)) == datetime(2024, 3, 11, 0, 0)
    days = next_fires("0 0 */10 * *", datetime(2024, 1, 1, 0, 0), 5)
    assert [d.day for d in days] == [11, 21, 31, 1, 11]


def test_a_step_on_month_starts_at_january():
    # */5 on month is 1, 6 and 11
    assert next_fire("0 0 1 */5 *", datetime(2024, 3, 15, 10, 30)) == datetime(2024, 6, 1, 0, 0)
    assert next_fire("0 0 1 */5 *", datetime(2024, 6, 1, 0, 0)) == datetime(2024, 11, 1, 0, 0)
    assert next_fire("0 0 1 */5 *", datetime(2024, 11, 1, 0, 0)) == datetime(2025, 1, 1, 0, 0)
    assert next_fire("0 0 1 */5 *", datetime(2024, 1, 1, 0, 0)) == datetime(2024, 6, 1, 0, 0)


def test_a_range_with_a_step_that_does_not_end_on_the_range_end():
    # 1-5/2 on day of week is Monday, Wednesday and Friday
    assert next_fire("0 0 * * 1-5/2", datetime(2024, 3, 15, 10, 30)) == datetime(2024, 3, 18, 0, 0)
    assert next_fire("0 0 * * 1-5/2", datetime(2024, 3, 18, 0, 0)) == datetime(2024, 3, 20, 0, 0)
    assert next_fire("0 0 * * 1-5/2", datetime(2024, 3, 20, 0, 0)) == datetime(2024, 3, 22, 0, 0)
    assert next_fire("0 0 2-12/4 * *", datetime(2024, 3, 2, 0, 0)) == datetime(2024, 3, 6, 0, 0)


def test_a_field_may_mix_items_of_every_kind():
    expr = "0,10-20/5,*/45 * * * *"  # 0, 10, 15, 20, 45
    moment = datetime(2024, 3, 15, 10, 0)
    minutes = []
    for _ in range(6):
        moment = next_fire(expr, moment)
        minutes.append(moment.minute)
    assert minutes == [10, 15, 20, 45, 0, 10]
