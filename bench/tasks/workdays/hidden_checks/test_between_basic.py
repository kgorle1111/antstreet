from datetime import date

from workdays import business_days_between

MON = date(2024, 1, 1)


def test_a_full_week_has_five_business_days():
    assert business_days_between(MON, date(2024, 1, 8)) == 5


def test_start_is_included_and_end_is_excluded():
    assert business_days_between(MON, date(2024, 1, 2)) == 1
    assert business_days_between(date(2024, 1, 2), MON) == -1
    assert business_days_between(MON, date(2024, 1, 5)) == 4
    assert business_days_between(MON, date(2024, 1, 6)) == 5


def test_same_day_is_zero():
    assert business_days_between(MON, MON) == 0
    assert business_days_between(date(2024, 1, 6), date(2024, 1, 6)) == 0


def test_weekends_do_not_count():
    assert business_days_between(date(2024, 1, 6), date(2024, 1, 8)) == 0
    assert business_days_between(date(2024, 1, 5), date(2024, 1, 6)) == 1
    assert business_days_between(date(2024, 1, 5), date(2024, 1, 8)) == 1
    assert business_days_between(date(2024, 1, 6), date(2024, 1, 9)) == 1


def test_ranges_that_start_and_end_mid_week():
    assert business_days_between(date(2024, 1, 3), date(2024, 1, 10)) == 5
    assert business_days_between(date(2024, 1, 4), date(2024, 1, 16)) == 8
    assert business_days_between(date(2024, 1, 5), date(2024, 1, 22)) == 11


def test_long_ranges():
    assert business_days_between(date(2024, 1, 1), date(2025, 1, 1)) == 262
    assert business_days_between(date(2024, 1, 1), date(2024, 1, 29)) == 20
    assert business_days_between(date(2020, 1, 1), date(2030, 1, 1)) == 2609


def test_default_holidays_is_empty():
    assert business_days_between(MON, date(2024, 1, 8), ()) == 5
    assert business_days_between(MON, date(2024, 1, 8), []) == 5
