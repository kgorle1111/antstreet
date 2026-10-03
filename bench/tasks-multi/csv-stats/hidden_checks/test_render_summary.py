from reader import read_table
from table import render_summary

CSV = "name,dept,salary,age\nAnn,eng,100,30\nBob,eng,120,\nCid,ops,80,41\nDee,ops,,28\n"

EXAMPLE = """column | count | missing |   mean |   min | median |    max | stdev
-------+-------+---------+--------+-------+--------+--------+------
salary |     3 |       1 | 100.00 | 80.00 | 100.00 | 120.00 | 20.00
age    |     3 |       1 |  33.00 | 28.00 |  30.00 |  41.00 |  7.00
"""


def test_example_from_the_idea_exactly():
    assert render_summary(read_table(CSV)) == EXAMPLE


def test_text_columns_are_left_out_and_order_is_table_order():
    table = read_table("z,label,a\n1,x,10\n2,y,20\n")
    lines = render_summary(table).splitlines()
    assert [line.split(" | ")[0].strip() for line in lines[2:]] == ["z", "a"]
    assert len(lines) == 4


def test_a_column_with_text_in_it_is_not_numeric():
    table = read_table("good,bad\n1,1\n2,two\n3,3\n")
    lines = render_summary(table).splitlines()
    assert len(lines) == 3
    assert lines[2].startswith("good")


def test_all_missing_column_is_left_out():
    table = read_table("a,b\n1,\n2,\n")
    lines = render_summary(table).splitlines()
    assert len(lines) == 3 and lines[2].startswith("a")


def test_no_numeric_column():
    assert render_summary(read_table("a,b\nx,y\nz,w\n")) == "No numeric columns.\n"
    assert render_summary(read_table("a,b\n")) == "No numeric columns.\n"
    assert render_summary(read_table("a,b\n,\n,\n")) == "No numeric columns.\n"


def test_single_number_has_a_dash_for_stdev():
    table = read_table("only\n5\n")
    assert render_summary(table) == (
        "column | count | missing | mean |  min | median |  max | stdev\n"
        "-------+-------+---------+------+------+--------+------+------\n"
        "only   |     1 |       0 | 5.00 | 5.00 |   5.00 | 5.00 | -\n"
    )


def test_counts_are_integers_and_a_blank_cell_is_missing():
    table = read_table("v\n1\n2\n \n4\n")
    assert render_summary(table) == (
        "column | count | missing | mean |  min | median |  max | stdev\n"
        "-------+-------+---------+------+------+--------+------+------\n"
        "v      |     3 |       1 | 2.33 | 1.00 |   2.00 | 4.00 |  1.53\n"
    )


def test_wide_values_widen_the_columns():
    table = read_table("big\n10000\n25000.5\n")
    assert render_summary(table) == (
        "column | count | missing |     mean |      min |   median |      max |    stdev\n"
        "-------+-------+---------+----------+----------+----------+----------+---------\n"
        "big    |     2 |       0 | 17500.25 | 10000.00 | 17500.25 | 25000.50 | 10606.96\n"
    )


def test_negative_numbers_and_quoted_names():
    table = read_table('"temp, C"\n-5\n"-1"\n3\n')
    assert render_summary(table) == (
        "column  | count | missing |  mean |   min | median |  max | stdev\n"
        "--------+-------+---------+-------+-------+--------+------+------\n"
        "temp, C |     3 |       0 | -1.00 | -5.00 |  -1.00 | 3.00 |  4.00\n"
    )


def test_two_numeric_columns_around_a_text_one():
    table = read_table("z,label,a\n1,x,10\n2,y,20\n")
    assert render_summary(table) == (
        "column | count | missing |  mean |   min | median |   max | stdev\n"
        "-------+-------+---------+-------+-------+--------+-------+------\n"
        "z      |     2 |       0 |  1.50 |  1.00 |   1.50 |  2.00 |  0.71\n"
        "a      |     2 |       0 | 15.00 | 10.00 |  15.00 | 20.00 |  7.07\n"
    )
