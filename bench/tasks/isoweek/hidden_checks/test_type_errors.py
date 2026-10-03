from datetime import date, datetime

import pytest
from isoweek import format_iso_week, iso_week, parse_iso_week, weeks_in_year

NOT_DATES = [
    datetime(2024, 3, 15),
    datetime(2024, 3, 15, 12, 30),
    "2024-03-15",
    20240315,
    None,
    (2024, 3, 15),
    1.5,
]


@pytest.mark.parametrize("value", NOT_DATES)
def test_iso_week_needs_a_date(value):
    with pytest.raises(TypeError):
        iso_week(value)


@pytest.mark.parametrize("value", NOT_DATES)
def test_format_iso_week_needs_a_date(value):
    with pytest.raises(TypeError):
        format_iso_week(value)


@pytest.mark.parametrize(
    "value", [None, 2024, 2024.0, b"2024-W11-5", ["2024-W11-5"], date(2024, 3, 15)]
)
def test_parse_iso_week_needs_a_str(value):
    with pytest.raises(TypeError):
        parse_iso_week(value)


@pytest.mark.parametrize("value", ["2020", 2020.0, 2020.5, None, True, False, [2020]])
def test_weeks_in_year_needs_an_int(value):
    with pytest.raises(TypeError):
        weeks_in_year(value)


@pytest.mark.parametrize("value", [0, -1, -2020, 10000, 123456])
def test_weeks_in_year_outside_one_to_9999_is_a_value_error(value):
    with pytest.raises(ValueError):
        weeks_in_year(value)


def test_the_edges_of_the_supported_years_are_valid():
    assert weeks_in_year(1) == 52
    assert weeks_in_year(9999) == 52


def test_a_plain_date_still_works_after_the_errors():
    assert iso_week(date(2021, 1, 3)) == (2020, 53)
    assert format_iso_week(date(2021, 1, 3)) == "2020-W53-7"
