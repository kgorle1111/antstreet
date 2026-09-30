from datetime import date

from workdays import add_business_days, business_days_between

MON = date(2024, 1, 1)
FRI = date(2024, 1, 5)


def test_a_holiday_is_skipped_going_forward():
    assert add_business_days(MON, 2, [date(2024, 1, 3)]) == date(2024, 1, 4)
    assert add_business_days(MON, 1, [date(2024, 1, 2)]) == date(2024, 1, 3)


def test_a_holiday_is_skipped_going_backward():
    assert add_business_days(FRI, -2, [date(2024, 1, 3)]) == date(2024, 1, 2)
    assert add_business_days(date(2024, 1, 8), -1, [FRI]) == date(2024, 1, 4)


def test_consecutive_holidays_and_holidays_next_to_a_weekend():
    holidays = [date(2024, 1, 5), date(2024, 1, 8), date(2024, 1, 9)]
    assert add_business_days(date(2024, 1, 4), 1, holidays) == date(2024, 1, 10)
    assert add_business_days(date(2024, 1, 10), -1, holidays) == date(2024, 1, 4)


def test_a_holiday_on_a_weekend_has_no_effect():
    assert add_business_days(FRI, 1, [date(2024, 1, 6), date(2024, 1, 7)]) == date(2024, 1, 8)
    assert add_business_days(date(2024, 1, 8), -1, [date(2024, 1, 6)]) == FRI


def test_the_start_date_being_a_holiday_does_not_change_the_count():
    assert add_business_days(MON, 1, [MON]) == date(2024, 1, 2)
    assert add_business_days(MON, -1, [MON]) == date(2023, 12, 29)


def test_zero_returns_the_start_even_when_it_is_a_holiday():
    assert add_business_days(MON, 0, [MON]) == MON


def test_a_date_listed_twice_is_skipped_once():
    assert add_business_days(MON, 2, [date(2024, 1, 3), date(2024, 1, 3)]) == date(2024, 1, 4)


def test_any_iterable_of_dates_is_accepted():
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    assert add_business_days(MON, 1, tuple(dates)) == date(2024, 1, 4)
    assert add_business_days(MON, 1, set(dates)) == date(2024, 1, 4)
    assert add_business_days(MON, 1, iter(dates)) == date(2024, 1, 4)
    assert add_business_days(MON, 3, (d for d in dates)) == date(2024, 1, 8)


def test_a_one_shot_generator_is_read_completely_before_stepping():
    def holidays():
        yield date(2024, 1, 10)
        yield date(2024, 1, 3)
        yield date(2024, 1, 4)

    assert add_business_days(MON, 6, holidays()) == date(2024, 1, 12)


def test_result_agrees_with_business_days_between():
    holidays = [date(2024, 1, 3), date(2024, 1, 17), date(2024, 1, 15), date(2024, 1, 20)]
    for start in [date(2024, 1, day) for day in range(1, 11)]:
        for n in (1, 2, 5, 9, 14):
            result = add_business_days(start, n, holidays)
            # Business days in (start, result] number exactly n.
            first = date.fromordinal(start.toordinal() + 1)
            last_exclusive = date.fromordinal(result.toordinal() + 1)
            assert business_days_between(first, last_exclusive, holidays) == n
            assert result not in holidays
        for n in (-1, -2, -5, -9):
            result = add_business_days(start, n, holidays)
            # Business days in [result, start) number exactly -n.
            assert business_days_between(result, start, holidays) == -n
            assert result not in holidays
