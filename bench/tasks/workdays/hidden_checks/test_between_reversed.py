from datetime import date

import pytest
from workdays import business_days_between


def test_end_before_start_gives_a_negative_count():
    assert business_days_between(date(2024, 1, 8), date(2024, 1, 1)) == -5
    assert business_days_between(date(2024, 1, 3), date(2024, 1, 2)) == -1


def test_reversed_range_is_the_exact_negation_of_the_forward_range():
    pairs = [
        (date(2024, 1, 1), date(2024, 1, 15)),
        (date(2024, 1, 5), date(2024, 1, 8)),
        (date(2024, 1, 6), date(2024, 1, 7)),
        (date(2024, 2, 27), date(2024, 3, 4)),
        (date(2023, 12, 29), date(2024, 1, 2)),
    ]
    for a, b in pairs:
        assert business_days_between(b, a) == -business_days_between(a, b)


def test_reversed_range_swaps_the_endpoints_before_applying_the_half_open_rule():
    # Forward, [Mon, Fri) holds Mon-Thu; reversed, the same four days give -4, not -5.
    assert business_days_between(date(2024, 1, 5), date(2024, 1, 1)) == -4
    assert business_days_between(date(2024, 1, 2), date(2024, 1, 1)) == -1
    assert business_days_between(date(2024, 1, 8), date(2024, 1, 5)) == -1


def test_reversed_range_with_only_weekend_days_is_zero():
    assert business_days_between(date(2024, 1, 8), date(2024, 1, 6)) == 0
    assert business_days_between(date(2024, 1, 7), date(2024, 1, 6)) == 0


def test_reversed_range_applies_holidays_to_the_swapped_range():
    holidays = [date(2024, 1, 3)]
    assert business_days_between(date(2024, 1, 8), date(2024, 1, 1), holidays) == -4
    # A holiday on the swapped range's excluded end has no effect.
    assert business_days_between(date(2024, 1, 3), date(2024, 1, 1), holidays) == -2
    # A holiday on the swapped range's included start does.
    assert business_days_between(date(2024, 1, 4), date(2024, 1, 3), holidays) == 0


@pytest.mark.parametrize("years", [1, 5])
def test_long_reversed_ranges(years):
    start = date(2020, 1, 1)
    end = date(2020 + years, 1, 1)
    assert business_days_between(end, start) == -business_days_between(start, end)
    assert business_days_between(end, start) < -200 * years
