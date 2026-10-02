from datetime import date

import pytest
from isoweek import format_iso_week, iso_week, parse_iso_week, weeks_in_year


def test_parse_of_format_is_the_same_date_over_several_years():
    day = date(1996, 1, 1).toordinal()
    for ordinal in range(day, date(2006, 1, 1).toordinal()):
        d = date.fromordinal(ordinal)
        assert parse_iso_week(format_iso_week(d)) == d


@pytest.mark.parametrize(
    "d",
    [
        date(1, 1, 1),
        date(1, 12, 31),
        date(999, 1, 1),
        date(1582, 10, 15),
        date(1900, 1, 1),
        date(2100, 12, 31),
        date(9998, 12, 31),
        date(9999, 1, 1),
        date(9999, 12, 31),
    ],
)
def test_round_trip_at_the_edges_of_history(d):
    assert parse_iso_week(format_iso_week(d)) == d


def test_the_text_agrees_with_iso_week_and_the_weekday():
    for ordinal in range(date(2019, 12, 1).toordinal(), date(2021, 2, 1).toordinal()):
        d = date.fromordinal(ordinal)
        year, week = iso_week(d)
        assert format_iso_week(d) == f"{year:04d}-W{week:02d}-{d.isoweekday()}"


def test_every_valid_week_of_a_long_and_a_short_year_parses_to_a_distinct_date():
    for year in (2020, 2021):
        dates = [
            parse_iso_week(f"{year}-W{week:02d}-{day}")
            for week in range(1, weeks_in_year(year) + 1)
            for day in range(1, 8)
        ]
        assert len(dates) == len(set(dates)) == 7 * weeks_in_year(year)
        assert dates == sorted(dates)
        assert all(iso_week(d)[0] == year for d in dates)
