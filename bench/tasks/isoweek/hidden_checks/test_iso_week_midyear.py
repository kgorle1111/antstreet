from datetime import date

import pytest
from isoweek import iso_week


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2024, 3, 15), (2024, 11)),
        (date(2023, 7, 4), (2023, 27)),
        (date(2024, 1, 1), (2024, 1)),
        (date(2024, 1, 7), (2024, 1)),
        (date(2024, 1, 8), (2024, 2)),
        (date(2026, 1, 1), (2026, 1)),
        (date(2026, 1, 4), (2026, 1)),
        (date(2026, 1, 5), (2026, 2)),
        (date(1900, 1, 1), (1900, 1)),
        (date(999, 6, 15), (999, 24)),
        (date(2020, 6, 30), (2020, 27)),
        (date(2015, 12, 31), (2015, 53)),
    ],
)
def test_iso_week_of_a_date(d, expected):
    assert iso_week(d) == expected


def test_result_is_a_tuple_of_two_ints():
    result = iso_week(date(2024, 3, 15))
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert all(type(part) is int for part in result)


def test_week_one_is_the_week_containing_january_4th():
    for year in range(1950, 2101):
        jan4 = date(year, 1, 4)
        assert iso_week(jan4) == (year, 1)
        monday = date.fromordinal(jan4.toordinal() - jan4.weekday())
        assert iso_week(monday) == (year, 1)
        assert iso_week(date.fromordinal(monday.toordinal() + 6)) == (year, 1)
        assert iso_week(date.fromordinal(monday.toordinal() + 7)) == (year, 2)


def test_the_week_changes_exactly_on_mondays():
    day = date(1999, 1, 1)
    end = date(2003, 1, 1)
    previous = iso_week(day)
    while day < end:
        day = date.fromordinal(day.toordinal() + 1)
        current = iso_week(day)
        if day.weekday() == 0:
            assert current != previous
            assert current in {(previous[0], previous[1] + 1), (previous[0] + 1, 1)}
        else:
            assert current == previous
        previous = current
