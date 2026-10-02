from datetime import datetime

import pytest
from cronnext import next_fire, next_fires

AFTER = datetime(2024, 3, 15, 10, 50)


def test_the_next_fire_times_in_order():
    assert next_fires("*/15 * * * *", AFTER, 4) == [
        datetime(2024, 3, 15, 11, 0),
        datetime(2024, 3, 15, 11, 15),
        datetime(2024, 3, 15, 11, 30),
        datetime(2024, 3, 15, 11, 45),
    ]


def test_the_first_is_strictly_after_and_each_is_next_fire_of_the_one_before():
    for expr in ("*/15 * * * *", "0 0 1 * *", "30 10 * * 1-5", "0 0 13 * 5"):
        fires = next_fires(expr, AFTER, 6)
        assert fires[0] == next_fire(expr, AFTER)
        for before, after in zip(fires, fires[1:], strict=False):
            assert after == next_fire(expr, before)
            assert after > before
        assert all(f > AFTER for f in fires)


def test_a_fire_exactly_on_after_is_not_the_first():
    fires = next_fires("0 * * * *", datetime(2024, 3, 15, 11, 0), 2)
    assert fires == [datetime(2024, 3, 15, 12, 0), datetime(2024, 3, 15, 13, 0)]


def test_one_fire_and_many_fires():
    assert next_fires("0 0 1 * *", datetime(2024, 11, 15, 0, 0), 1) == [datetime(2024, 12, 1, 0, 0)]
    fires = next_fires("0 0 1 * *", datetime(2024, 11, 15, 0, 0), 3)
    assert fires == [
        datetime(2024, 12, 1, 0, 0),
        datetime(2025, 1, 1, 0, 0),
        datetime(2025, 2, 1, 0, 0),
    ]
    assert len(next_fires("* * * * *", AFTER, 100)) == 100


def test_the_result_is_a_list_of_naive_datetimes():
    fires = next_fires("0 * * * *", AFTER, 3)
    assert type(fires) is list
    assert all(type(f) is datetime and f.tzinfo is None for f in fires)


def test_count_zero_gives_an_empty_list_and_does_not_search():
    assert next_fires("* * * * *", AFTER, 0) == []
    assert next_fires("0 0 31 2 *", AFTER, 0) == []


def test_count_zero_still_checks_the_expression():
    for bad in ("", "* * * *", "60 * * * *", "a b c d e"):
        with pytest.raises(ValueError):
            next_fires(bad, AFTER, 0)
    with pytest.raises(TypeError):
        next_fires(None, AFTER, 0)


@pytest.mark.parametrize("count", [-1, -5, -100])
def test_a_negative_count_is_a_value_error(count):
    with pytest.raises(ValueError):
        next_fires("* * * * *", AFTER, count)


@pytest.mark.parametrize("count", [1.0, 2.5, "3", None, True, False, [3]])
def test_a_count_that_is_not_an_int_is_a_type_error(count):
    with pytest.raises(TypeError):
        next_fires("* * * * *", AFTER, count)


def test_an_expression_that_never_fires_is_a_value_error_unless_count_is_zero():
    with pytest.raises(ValueError):
        next_fires("0 0 31 2 *", AFTER, 1)
    with pytest.raises(ValueError):
        next_fires("0 0 30 2 *", AFTER, 3)


def test_every_weekday_morning_for_two_weeks():
    fires = next_fires("30 8 * * 1-5", datetime(2024, 3, 15, 9, 0), 6)
    assert fires == [
        datetime(2024, 3, 18, 8, 30),
        datetime(2024, 3, 19, 8, 30),
        datetime(2024, 3, 20, 8, 30),
        datetime(2024, 3, 21, 8, 30),
        datetime(2024, 3, 22, 8, 30),
        datetime(2024, 3, 25, 8, 30),
    ]
