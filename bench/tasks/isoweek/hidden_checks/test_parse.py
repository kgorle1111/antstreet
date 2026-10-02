from datetime import date

import pytest
from isoweek import parse_iso_week


@pytest.mark.parametrize(
    ("text", "d"),
    [
        ("2020-W53-7", date(2021, 1, 3)),
        ("2021-W01-1", date(2021, 1, 4)),
        ("2024-W11-5", date(2024, 3, 15)),
        ("2026-W01-4", date(2026, 1, 1)),
        ("2015-W53-4", date(2015, 12, 31)),
        ("2009-W01-1", date(2008, 12, 29)),
        ("2025-W01-1", date(2024, 12, 30)),
        ("1999-W52-6", date(2000, 1, 1)),
        ("0001-W01-1", date(1, 1, 1)),
        ("0999-W24-6", date(999, 6, 15)),
        ("9999-W52-5", date(9999, 12, 31)),
    ],
)
def test_parse_of_a_week_date(text, d):
    assert parse_iso_week(text) == d


def test_week_53_is_valid_in_a_long_year():
    assert parse_iso_week("2020-W53-1") == date(2020, 12, 28)
    assert parse_iso_week("2004-W53-7") == date(2005, 1, 2)


def test_result_is_a_plain_date():
    result = parse_iso_week("2024-W11-5")
    assert type(result) is date


def test_every_weekday_of_one_week():
    days = [parse_iso_week(f"2024-W11-{n}") for n in range(1, 8)]
    assert days == [date(2024, 3, n) for n in range(11, 18)]
