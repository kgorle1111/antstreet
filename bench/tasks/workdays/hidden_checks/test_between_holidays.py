from datetime import date

from workdays import business_days_between

MON = date(2024, 1, 1)
NEXT_MON = date(2024, 1, 8)


def test_a_weekday_holiday_is_not_counted():
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 3)]) == 4
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 3), date(2024, 1, 4)]) == 3


def test_a_weekend_holiday_does_not_count_twice():
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 6)]) == 5
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 6), date(2024, 1, 7)]) == 5
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 6), date(2024, 1, 3)]) == 4


def test_a_date_listed_twice_counts_once():
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 3), date(2024, 1, 3)]) == 4
    assert business_days_between(MON, NEXT_MON, (date(2024, 1, 3),) * 3) == 4


def test_holidays_outside_the_range_have_no_effect():
    assert business_days_between(MON, NEXT_MON, [date(2023, 12, 29)]) == 5
    assert business_days_between(MON, NEXT_MON, [date(2024, 1, 9), date(2025, 1, 3)]) == 5


def test_holiday_on_start_is_removed_and_holiday_on_end_is_not():
    assert business_days_between(MON, NEXT_MON, [MON]) == 4
    assert business_days_between(MON, NEXT_MON, [NEXT_MON]) == 5
    assert business_days_between(MON, date(2024, 1, 2), [MON]) == 0


def test_every_business_day_a_holiday_gives_zero():
    week = [date(2024, 1, day) for day in range(1, 6)]
    assert business_days_between(MON, NEXT_MON, week) == 0


def test_any_iterable_of_dates_is_accepted():
    dates = [date(2024, 1, 3), date(2024, 1, 4)]
    assert business_days_between(MON, NEXT_MON, tuple(dates)) == 3
    assert business_days_between(MON, NEXT_MON, set(dates)) == 3
    assert business_days_between(MON, NEXT_MON, frozenset(dates)) == 3
    assert business_days_between(MON, NEXT_MON, iter(dates)) == 3
    assert business_days_between(MON, NEXT_MON, (d for d in dates)) == 3
    assert business_days_between(MON, NEXT_MON, dict.fromkeys(dates)) == 3


def test_a_one_shot_generator_with_duplicates_and_out_of_range_dates():
    def holidays():
        yield date(2023, 12, 25)
        yield date(2024, 1, 2)
        yield date(2024, 1, 2)
        yield date(2024, 1, 6)
        yield date(2024, 1, 8)

    assert business_days_between(MON, NEXT_MON, holidays()) == 4


def test_holidays_over_a_long_range():
    holidays = [date(2024, 1, 1), date(2024, 7, 4), date(2024, 12, 25), date(2024, 5, 25)]
    assert business_days_between(date(2024, 1, 1), date(2025, 1, 1), holidays) == 259
