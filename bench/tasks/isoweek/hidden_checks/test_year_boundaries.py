from datetime import date

import pytest
from isoweek import iso_week, weeks_in_year


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2021, 1, 1), (2020, 53)),
        (date(2021, 1, 3), (2020, 53)),
        (date(2021, 1, 4), (2021, 1)),
        (date(2016, 1, 1), (2015, 53)),
        (date(2010, 1, 3), (2009, 53)),
        (date(2012, 1, 1), (2011, 52)),
        (date(2000, 1, 1), (1999, 52)),
        (date(2027, 1, 1), (2026, 53)),
        (date(2100, 1, 1), (2099, 53)),
        (date(2005, 1, 1), (2004, 53)),
        (date(2005, 1, 2), (2004, 53)),
        (date(2005, 1, 3), (2005, 1)),
    ],
)
def test_early_january_can_belong_to_the_previous_iso_year(d, expected):
    assert iso_week(d) == expected


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2018, 12, 31), (2019, 1)),
        (date(2019, 12, 30), (2020, 1)),
        (date(2019, 12, 31), (2020, 1)),
        (date(2008, 12, 29), (2009, 1)),
        (date(2024, 12, 30), (2025, 1)),
        (date(2024, 12, 29), (2024, 52)),
        (date(2004, 12, 31), (2004, 53)),
        (date(1999, 12, 31), (1999, 52)),
        (date(2020, 12, 31), (2020, 53)),
    ],
)
def test_late_december_can_belong_to_the_next_iso_year(d, expected):
    assert iso_week(d) == expected


def test_the_last_day_before_week_one_is_in_the_last_week_of_the_previous_year():
    for year in range(1901, 2100):
        jan4 = date(year, 1, 4)
        monday = date.fromordinal(jan4.toordinal() - jan4.weekday())
        before = date.fromordinal(monday.toordinal() - 1)
        assert iso_week(before) == (year - 1, weeks_in_year(year - 1))
        # and the week before that is exactly one week earlier
        week_before = date.fromordinal(monday.toordinal() - 8)
        assert iso_week(week_before) == (year - 1, weeks_in_year(year - 1) - 1)


def test_calendar_year_and_iso_year_differ_only_around_new_year():
    day = date(1998, 1, 1)
    while day < date(2004, 1, 1):
        iso_year, week = iso_week(day)
        if iso_year != day.year:
            if day.month == 1:
                assert iso_year == day.year - 1
                assert week >= 52
            else:
                assert day.month == 12
                assert iso_year == day.year + 1
                assert week == 1
        day = date.fromordinal(day.toordinal() + 1)
