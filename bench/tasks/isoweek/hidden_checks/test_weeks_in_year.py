from datetime import date

import pytest
from isoweek import iso_week, weeks_in_year

LONG_YEARS = {1992, 1998, 2004, 2009, 2015, 2020, 2026, 2032, 2037, 2043}


@pytest.mark.parametrize("year", sorted(LONG_YEARS))
def test_long_years_have_53_weeks(year):
    assert weeks_in_year(year) == 53


@pytest.mark.parametrize("year", [y for y in range(1990, 2046) if y not in LONG_YEARS])
def test_other_years_have_52_weeks(year):
    assert weeks_in_year(year) == 52


@pytest.mark.parametrize(
    ("year", "weeks"), [(1, 52), (1900, 52), (2000, 52), (2100, 52), (2099, 53), (9999, 52)]
)
def test_far_years(year, weeks):
    assert weeks_in_year(year) == weeks


def test_the_year_starting_on_a_thursday_and_the_leap_year_starting_on_a_wednesday_are_long():
    assert date(2015, 1, 1).weekday() == 3
    assert weeks_in_year(2015) == 53
    assert date(2020, 1, 1).weekday() == 2
    assert weeks_in_year(2020) == 53
    # a non-leap year starting on a Wednesday is short
    assert date(2014, 1, 1).weekday() == 2
    assert weeks_in_year(2014) == 52


def test_the_last_week_number_exists_and_one_more_does_not():
    for year in range(1950, 2101):
        jan4 = date(year + 1, 1, 4)
        monday = date.fromordinal(jan4.toordinal() - jan4.weekday())
        last_day = date.fromordinal(monday.toordinal() - 1)
        assert iso_week(last_day) == (year, weeks_in_year(year))
        assert weeks_in_year(year) in (52, 53)


def test_result_is_an_int():
    assert type(weeks_in_year(2020)) is int
