from datetime import date

import pytest
from workdays import add_months


def test_forward_within_a_year():
    assert add_months(date(2024, 1, 15), 1) == date(2024, 2, 15)
    assert add_months(date(2024, 1, 15), 5) == date(2024, 6, 15)


def test_zero_months_returns_the_same_date():
    assert add_months(date(2024, 6, 15), 0) == date(2024, 6, 15)


def test_rolls_over_the_year_boundary_forward():
    assert add_months(date(2024, 11, 20), 2) == date(2025, 1, 20)
    assert add_months(date(2024, 12, 5), 1) == date(2025, 1, 5)
    assert add_months(date(2024, 1, 10), 25) == date(2026, 2, 10)


def test_rolls_over_the_year_boundary_backward():
    assert add_months(date(2024, 1, 20), -1) == date(2023, 12, 20)
    assert add_months(date(2024, 2, 5), -2) == date(2023, 12, 5)
    assert add_months(date(2024, 3, 10), -27) == date(2021, 12, 10)


def test_whole_years():
    assert add_months(date(2024, 6, 15), 12) == date(2025, 6, 15)
    assert add_months(date(2024, 6, 15), -12) == date(2023, 6, 15)
    assert add_months(date(2024, 12, 31), -12) == date(2023, 12, 31)


def test_december_is_month_twelve():
    assert add_months(date(2024, 12, 15), 0) == date(2024, 12, 15)
    assert add_months(date(2024, 11, 15), 1) == date(2024, 12, 15)
    assert add_months(date(2024, 1, 15), -1) == date(2023, 12, 15)
    assert add_months(date(2024, 12, 15), 12) == date(2025, 12, 15)
    assert add_months(date(2025, 1, 15), -13) == date(2023, 12, 15)


def test_returns_a_plain_date():
    result = add_months(date(2024, 1, 15), 1)
    assert type(result) is date


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2023, 1, 31), 1, date(2023, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2024, 3, 31), -1, date(2024, 2, 29)),
        (date(2023, 3, 31), -1, date(2023, 2, 28)),
        (date(2024, 8, 31), 1, date(2024, 9, 30)),
        (date(2024, 5, 31), -1, date(2024, 4, 30)),
        (date(2024, 10, 30), 4, date(2025, 2, 28)),
        (date(2024, 1, 29), 13, date(2025, 2, 28)),
        (date(2024, 12, 31), 2, date(2025, 2, 28)),
        (date(2024, 12, 31), -1, date(2024, 11, 30)),
    ],
)
def test_day_is_clamped_to_the_last_day_of_the_target_month(start, months, expected):
    assert add_months(start, months) == expected


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(1900, 1, 31), 1, date(1900, 2, 28)),
        (date(2000, 1, 31), 1, date(2000, 2, 29)),
        (date(2100, 1, 31), 1, date(2100, 2, 28)),
        (date(2024, 2, 29), 12, date(2025, 2, 28)),
        (date(2024, 2, 29), 48, date(2028, 2, 29)),
        (date(2024, 2, 29), -12, date(2023, 2, 28)),
        (date(2024, 2, 29), 1, date(2024, 3, 29)),
    ],
)
def test_leap_years_follow_the_gregorian_rule(start, months, expected):
    assert add_months(start, months) == expected


def test_every_result_is_computed_from_the_original_date():
    assert add_months(date(2024, 1, 31), 2) == date(2024, 3, 31)
    assert add_months(date(2023, 1, 31), 3) == date(2023, 4, 30)
    assert add_months(date(2024, 3, 31), -2) == date(2024, 1, 31)
    assert add_months(date(2024, 1, 30), 13) == date(2025, 2, 28)


def test_a_short_month_end_does_not_become_the_end_of_the_next_month():
    assert add_months(date(2023, 2, 28), 1) == date(2023, 3, 28)
    assert add_months(date(2024, 2, 28), 1) == date(2024, 3, 28)
    assert add_months(date(2024, 4, 30), 1) == date(2024, 5, 30)


def test_a_day_that_fits_is_never_changed():
    assert add_months(date(2024, 1, 28), 1) == date(2024, 2, 28)
    assert add_months(date(2024, 1, 29), 1) == date(2024, 2, 29)
    assert add_months(date(2023, 1, 30), 2) == date(2023, 3, 30)
