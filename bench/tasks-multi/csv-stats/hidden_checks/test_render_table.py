import pytest
from table import render_table


def test_text_columns_are_left_aligned():
    text = render_table(["name", "city"], [["Ann", "Oslo"], ["Bartholomew", "Rome"]])
    assert text == (
        "name        | city\n------------+-----\nAnn         | Oslo\nBartholomew | Rome\n"
    )


def test_number_columns_are_right_aligned_with_the_header():
    text = render_table(["item", "qty", "price"], [["bolt", 5, 0.5], ["nut", 120, 12.25]])
    assert text == (
        "item | qty | price\n-----+-----+------\nbolt |   5 |  0.50\nnut  | 120 | 12.25\n"
    )


def test_mixed_column_is_left_aligned():
    text = render_table(["v"], [[1], ["n/a"], [22]])
    assert text == "v\n---\n1\nn/a\n22\n"


def test_bool_does_not_count_as_a_number():
    text = render_table(["flag", "n"], [[True, 1], [False, 22]])
    assert text == "flag  |  n\n------+---\nTrue  |  1\nFalse | 22\n"


def test_none_is_a_dash_and_does_not_stop_right_alignment():
    text = render_table(["a", "b"], [[None, 1.5], [2, None], [30, 4]])
    assert text == " a |    b\n---+-----\n - | 1.50\n 2 |    -\n30 |    4\n"


def test_a_column_of_only_none_is_left_aligned():
    text = render_table(["x", "y"], [[1, None], [2, None]])
    assert text == "x | y\n--+--\n1 | -\n2 | -\n"


def test_no_rows_gives_header_and_separator():
    assert render_table(["alpha", "b"], []) == "alpha | b\n------+--\n"


def test_no_line_has_trailing_spaces():
    text = render_table(["name", "note"], [["a", ""], ["bb", "long note"], ["ccc", ""]])
    for line in text.splitlines():
        assert line == line.rstrip()
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert text.splitlines()[2] == "a    |"


def test_floats_use_format_value_and_other_values_use_str():
    text = render_table(["a"], [[1.0], [-0.0], [2.345]])
    assert text == "   a\n----\n1.00\n0.00\n2.35\n"


def test_header_wider_than_every_cell():
    text = render_table(["quantity"], [[1], [2]])
    assert text == "quantity\n--------\n       1\n       2\n"


def test_three_columns_separator_shape():
    text = render_table(["a", "bb", "ccc"], [["x", "y", "z"]])
    assert text == "a | bb | ccc\n--+----+----\nx | y  | z\n"


def test_errors():
    with pytest.raises(ValueError):
        render_table([], [])
    with pytest.raises(ValueError):
        render_table(["a", "b"], [[1]])
    with pytest.raises(ValueError):
        render_table(["a"], [[1, 2]])
    with pytest.raises(ValueError):
        render_table(["a"], [[1], []])


def test_inputs_may_be_tuples_and_are_not_modified():
    columns = ("a", "b")
    rows = [(1, 2), (3, 4)]
    text = render_table(columns, rows)
    assert text == "a | b\n--+--\n1 | 2\n3 | 4\n"
    assert rows == [(1, 2), (3, 4)]
