from datetime import date

import pytest
from isoweek import format_iso_week


@pytest.mark.parametrize(
    ("d", "text"),
    [
        (date(2021, 1, 3), "2020-W53-7"),
        (date(2021, 1, 4), "2021-W01-1"),
        (date(2024, 3, 15), "2024-W11-5"),
        (date(2024, 12, 30), "2025-W01-1"),
        (date(2024, 12, 29), "2024-W52-7"),
        (date(2026, 1, 1), "2026-W01-4"),
        (date(2015, 12, 31), "2015-W53-4"),
        (date(2000, 1, 1), "1999-W52-6"),
        (date(2008, 12, 29), "2009-W01-1"),
        (date(2023, 7, 4), "2023-W27-2"),
    ],
)
def test_format_of_a_date(d, text):
    assert format_iso_week(d) == text


@pytest.mark.parametrize(
    ("d", "text"),
    [
        (date(1, 1, 1), "0001-W01-1"),
        (date(999, 6, 15), "0999-W24-6"),
        (date(99, 3, 3), "0099-W10-2"),
    ],
)
def test_the_year_is_padded_to_four_digits(d, text):
    assert format_iso_week(d) == text


def test_the_week_is_padded_to_two_digits_and_the_weekday_is_one_digit():
    assert format_iso_week(date(2024, 1, 1)) == "2024-W01-1"
    assert format_iso_week(date(2024, 2, 5)) == "2024-W06-1"
    assert format_iso_week(date(2024, 3, 11)) == "2024-W11-1"


def test_every_weekday_of_one_week():
    week = [format_iso_week(date(2024, 3, day)) for day in range(11, 18)]
    assert week == [f"2024-W11-{n}" for n in range(1, 8)]


def test_the_iso_year_not_the_calendar_year_is_printed():
    assert format_iso_week(date(2027, 1, 1)).startswith("2026-")
    assert format_iso_week(date(2019, 12, 31)).startswith("2020-")


def test_result_is_a_str_without_spaces():
    text = format_iso_week(date(2024, 3, 15))
    assert isinstance(text, str)
    assert " " not in text
    assert len(text) == 10
