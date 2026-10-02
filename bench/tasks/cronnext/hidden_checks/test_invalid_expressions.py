from datetime import datetime

import pytest
from cronnext import next_fire

AFTER = datetime(2024, 3, 15, 10, 30)


def rejected(expr):
    with pytest.raises(ValueError):
        next_fire(expr, AFTER)


@pytest.mark.parametrize(
    "expr",
    [
        "",
        " ",
        "\t",
        "* * * *",
        "* * * * * *",
        "*",
        "* *",
        "1 2 3 4",
        "0 0 1 1 * *",
        "* * * * * 2024",
    ],
)
def test_the_wrong_number_of_fields(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "expr",
    [
        "60 * * * *",
        "-1 * * * *",
        "100 * * * *",
        "* 24 * * *",
        "* 25 * * *",
        "* * 0 * *",
        "* * 32 * *",
        "* * * 0 *",
        "* * * 13 *",
        "* * * * 7",
        "* * * * 8",
        "0-60 * * * *",
        "* 0-24 * * *",
        "* * 0-31 * *",
        "* * 1-32 * *",
        "* * * 1-13 *",
        "* * * * 0-7",
        "0,60 * * * *",
        "* * * * 1,7",
    ],
)
def test_values_outside_the_range_of_the_field(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "expr",
    ["5-1 * * * *", "* 23-0 * * *", "* * 31-1 * *", "* * * 12-1 *", "* * * * 6-0", "30-29 * * * *"],
)
def test_reversed_ranges(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "expr",
    ["*/0 * * * *", "1-5/0 * * * *", "* */0 * * *", "* * */0 * *", "* * * */0 *", "* * * * */0"],
)
def test_a_step_of_zero(expr):
    rejected(expr)


@pytest.mark.parametrize("expr", ["5/10 * * * *", "* 3/2 * * *", "* * 1/5 * *", "* * * 1/2 *"])
def test_a_step_on_a_single_number(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "expr",
    [
        "1,,2 * * * *",
        ",1 * * * *",
        "1, * * * *",
        ",, * * * *",
        ", * * * *",
        "* 1,,2 * * *",
        "* * * * 1,",
    ],
)
def test_empty_items(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "expr",
    [
        "a * * * *",
        "* * * JAN *",
        "* * * * MON",
        "* * * * mon",
        "* * * jan-mar *",
        "@daily",
        "@hourly",
        "@reboot",
        "? * * * *",
        "* * ? * *",
        "* * * * ?",
        "L * * * *",
        "* * L * *",
        "+5 * * * *",
        "1.5 * * * *",
        "1e1 * * * *",
        "0x5 * * * *",
        "1_0 * * * *",
        "** * * * *",
        "*/ * * * *",
        "/5 * * * *",
        "*/5/2 * * * *",
        "1-2-3 * * * *",
        "1- * * * *",
        "-5 * * * *",
        "*-5 * * * *",
        "1-* * * * *",
        "*/-1 * * * *",
        "*/+1 * * * *",
        "*/a * * * *",
        "*/1.5 * * * *",
        "1 - 5 * * * *",
        "(1) * * * *",
        "1;2 * * * *",
        "1|2 * * * *",
    ],
)
def test_text_that_is_not_part_of_the_subset(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "expr", ["٣ * * * *", "* ٣ * * *", "*/٣ * * * *", "１ * * * *", "* * ３ * *"]
)
def test_non_ascii_digits_are_rejected(expr):
    rejected(expr)


@pytest.mark.parametrize(
    "value", [None, 5, 1.5, b"* * * * *", ["*", "*", "*", "*", "*"], ("* * * * *",)]
)
def test_an_expression_that_is_not_a_str_is_a_type_error(value):
    with pytest.raises(TypeError):
        next_fire(value, AFTER)


@pytest.mark.parametrize(
    "expr",
    [
        "0 0 1 1 *",
        "59 23 31 12 6",
        "0-59 0-23 1-31 1-12 0-6",
        "*/59 */23 */31 */12 */6",
        "0,59 0,23 1,31 1,12 0,6",
        "00 00 01 01 00",
    ],
)
def test_the_edges_of_every_range_are_valid(expr):
    assert next_fire(expr, AFTER) > AFTER
