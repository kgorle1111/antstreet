from datetime import date

from workdays import add_business_days

MON = date(2024, 1, 1)
FRI = date(2024, 1, 5)
SAT = date(2024, 1, 6)
SUN = date(2024, 1, 7)


def test_forward_within_a_week():
    assert add_business_days(MON, 1) == date(2024, 1, 2)
    assert add_business_days(MON, 4) == FRI
    assert add_business_days(date(2024, 1, 3), 2) == FRI


def test_forward_over_a_weekend():
    assert add_business_days(FRI, 1) == date(2024, 1, 8)
    assert add_business_days(FRI, 2) == date(2024, 1, 9)
    assert add_business_days(date(2024, 1, 4), 3) == date(2024, 1, 9)


def test_whole_weeks():
    assert add_business_days(MON, 5) == date(2024, 1, 8)
    assert add_business_days(MON, 10) == date(2024, 1, 15)
    assert add_business_days(MON, 260) == date(2024, 12, 30)


def test_backward():
    assert add_business_days(date(2024, 1, 8), -1) == FRI
    assert add_business_days(date(2024, 1, 3), -3) == date(2023, 12, 29)
    assert add_business_days(date(2024, 1, 8), -5) == MON
    assert add_business_days(FRI, -4) == MON


def test_starting_on_a_weekend_the_start_day_is_not_counted():
    assert add_business_days(SAT, 1) == date(2024, 1, 8)
    assert add_business_days(SUN, 1) == date(2024, 1, 8)
    assert add_business_days(SAT, 2) == date(2024, 1, 9)
    assert add_business_days(SAT, -1) == FRI
    assert add_business_days(SUN, -1) == FRI
    assert add_business_days(SUN, -2) == date(2024, 1, 4)


def test_starting_on_a_business_day_the_start_day_is_not_counted():
    assert add_business_days(FRI, -1) == date(2024, 1, 4)
    assert add_business_days(MON, -1) == date(2023, 12, 29)


def test_zero_returns_the_start_unchanged():
    assert add_business_days(MON, 0) == MON
    assert add_business_days(SAT, 0) == SAT
    assert add_business_days(SUN, 0) == SUN


def test_result_is_always_a_business_day_when_n_is_not_zero():
    for start in [date(2024, 1, day) for day in range(1, 15)]:
        for n in (-7, -3, -1, 1, 2, 6, 11):
            result = add_business_days(start, n)
            assert result.weekday() < 5
            assert (result > start) == (n > 0)
