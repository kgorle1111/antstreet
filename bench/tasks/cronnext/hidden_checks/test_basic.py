from datetime import datetime

import pytest
from cronnext import next_fire

AFTER = datetime(2024, 3, 15, 10, 30)  # a Friday


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("* * * * *", datetime(2024, 3, 15, 10, 31)),
        ("*/15 * * * *", datetime(2024, 3, 15, 10, 45)),
        ("0 * * * *", datetime(2024, 3, 15, 11, 0)),
        ("45 * * * *", datetime(2024, 3, 15, 10, 45)),
        ("0 12 * * *", datetime(2024, 3, 15, 12, 0)),
        ("0 9 * * *", datetime(2024, 3, 16, 9, 0)),
        ("45 23 * * *", datetime(2024, 3, 15, 23, 45)),
        ("15 14 1 * *", datetime(2024, 4, 1, 14, 15)),
        ("0 0 1 1 *", datetime(2025, 1, 1, 0, 0)),
        ("0 0 15 * *", datetime(2024, 4, 15, 0, 0)),
        ("31 10 15 3 *", datetime(2024, 3, 15, 10, 31)),
        ("0 0 25 12 *", datetime(2024, 12, 25, 0, 0)),
        ("5 4 * * *", datetime(2024, 3, 16, 4, 5)),
    ],
)
def test_simple_expressions(expr, expected):
    assert next_fire(expr, AFTER) == expected


def test_the_result_is_a_naive_datetime_on_a_whole_minute():
    result = next_fire("*/7 * * * *", datetime(2024, 3, 15, 10, 30, 12, 345))
    assert type(result) is datetime
    assert result.tzinfo is None
    assert (result.second, result.microsecond) == (0, 0)


def test_every_minute_steps_one_minute_at_a_time():
    moment = datetime(2024, 3, 15, 23, 58)
    seen = []
    for _ in range(4):
        moment = next_fire("* * * * *", moment)
        seen.append(moment)
    assert seen == [
        datetime(2024, 3, 15, 23, 59),
        datetime(2024, 3, 16, 0, 0),
        datetime(2024, 3, 16, 0, 1),
        datetime(2024, 3, 16, 0, 2),
    ]


@pytest.mark.parametrize(
    "expr",
    [
        "  30 10 * * *  ",
        "30\t10\t*\t*\t*",
        "30   10   *   *   *",
        "30 \t 10 * * *",
        "\t30 10 * * *\n",
    ],
)
def test_any_spaces_or_tabs_between_fields_and_around_the_expression(expr):
    assert next_fire(expr, datetime(2024, 3, 15, 9, 0)) == datetime(2024, 3, 15, 10, 30)


@pytest.mark.parametrize("expr", ["05 09 * * *", "5 9 * * *", "005 009 * * *"])
def test_leading_zeros_are_fine(expr):
    assert next_fire(expr, datetime(2024, 3, 15, 0, 0)) == datetime(2024, 3, 15, 9, 5)
