import pytest
from reader import read_table
from stats import describe


def test_column_returns_strings_in_row_order_and_a_new_list():
    table = read_table("a,b\n1,x\n2,y\n3,z\n")
    column = table.column("b")
    assert column == ["x", "y", "z"]
    column.clear()
    assert table.column("b") == ["x", "y", "z"]
    assert table.column("a") == ["1", "2", "3"]


def test_unknown_column():
    table = read_table("a\n1\n")
    with pytest.raises(KeyError):
        table.column("z")
    with pytest.raises(KeyError):
        table.numbers("z")
    with pytest.raises(KeyError):
        table.column("A")


def test_numbers_are_floats_and_blanks_are_none():
    table = read_table("v\n1\n 2.5 \n\n-3\n+4\n.5\n5.\n1e3\n2E-2\n  \n0\n-0.0\n")
    # the empty line is skipped, the line of spaces is a missing value
    assert table.numbers("v") == [1.0, 2.5, -3.0, 4.0, 0.5, 5.0, 1000.0, 0.02, None, 0.0, 0.0]
    assert all(isinstance(n, float) for n in table.numbers("v") if n is not None)


def test_empty_field_is_missing_in_a_wider_table():
    table = read_table("a,b\n1,\n,2\n3,4\n")
    assert table.numbers("a") == [1.0, None, 3.0]
    assert table.numbers("b") == [None, 2.0, 4.0]


@pytest.mark.parametrize(
    "bad",
    [
        "abc",
        "1,000",
        "1_000",
        "nan",
        "NaN",
        "inf",
        "-inf",
        "Infinity",
        "0x10",
        "1.2.3",
        "--1",
        "1e",
        "e5",
        "1 2",
        "$5",
        "1e999",
    ],
)
def test_non_numbers_raise_value_error(bad):
    table = read_table(f'v\n1\n"{bad}"\n2\n')
    with pytest.raises(ValueError):
        table.numbers("v")
    assert table.column("v") == ["1", bad, "2"]


def test_numbers_checks_the_whole_column_but_other_columns_are_fine():
    table = read_table("name,n\nann,1\nbob,x\n")
    with pytest.raises(ValueError):
        table.numbers("n")
    assert table.column("name") == ["ann", "bob"]


def test_numbers_feed_describe():
    table = read_table("a\n1\n2\n\n4\n")
    summary = describe(table.numbers("a"))
    assert (summary.count, summary.missing) == (3, 0)
    assert summary.mean == pytest.approx(7 / 3)
