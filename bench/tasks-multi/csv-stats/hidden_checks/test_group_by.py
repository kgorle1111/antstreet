import pytest
from reader import read_table
from stats import group_by

CSV = "name,dept,salary,age\nAnn,eng,100,30\nBob,eng,120,\nCid,ops,80,41\nDee,ops,,28\n"


@pytest.fixture
def table():
    return read_table(CSV)


def test_sum_is_the_default(table):
    assert group_by(table, "dept", "salary") == {"eng": 220.0, "ops": 80.0}
    assert group_by(table, "dept", "salary", "sum") == {"eng": 220.0, "ops": 80.0}
    assert all(isinstance(v, float) for v in group_by(table, "dept", "salary").values())


def test_mean_skips_missing_values(table):
    assert group_by(table, "dept", "salary", "mean") == {"eng": 110.0, "ops": 80.0}
    assert group_by(table, "dept", "age", "mean") == {"eng": 30.0, "ops": 34.5}


def test_count_counts_numbers_only_and_is_an_int(table):
    result = group_by(table, "dept", "age", "count")
    assert result == {"eng": 1, "ops": 2}
    assert all(type(v) is int for v in result.values())
    assert group_by(table, "dept", "salary", "count") == {"eng": 2, "ops": 1}


def test_min_and_max(table):
    assert group_by(table, "dept", "salary", "min") == {"eng": 100.0, "ops": 80.0}
    assert group_by(table, "dept", "salary", "max") == {"eng": 120.0, "ops": 80.0}
    assert group_by(table, "dept", "age", "max") == {"eng": 30.0, "ops": 41.0}


def test_groups_come_in_order_of_first_appearance():
    table = read_table("k,v\nz,1\na,2\nz,3\nm,4\na,5\n")
    result = group_by(table, "k", "v")
    assert list(result) == ["z", "a", "m"]
    assert result == {"z": 4.0, "a": 7.0, "m": 4.0}


def test_groups_with_no_numbers():
    table = read_table("k,v\na,\nb,5\na,\n")
    assert group_by(table, "k", "v", "sum") == {"a": 0.0, "b": 5.0}
    assert group_by(table, "k", "v", "count") == {"a": 0, "b": 1}
    assert group_by(table, "k", "v", "mean") == {"a": None, "b": 5.0}
    assert group_by(table, "k", "v", "min") == {"a": None, "b": 5.0}
    assert group_by(table, "k", "v", "max") == {"a": None, "b": 5.0}


def test_empty_string_is_a_group_and_keys_are_exact():
    table = read_table("k,v\n,1\nA,2\na,3\n,4\n a,5\n")
    assert group_by(table, "k", "v") == {"": 5.0, "A": 2.0, "a": 3.0, " a": 5.0}


def test_grouping_by_the_value_column_itself():
    table = read_table("v\n1\n1\n2\n")
    assert group_by(table, "v", "v", "count") == {"1": 2, "2": 1}


def test_a_table_without_rows_gives_no_groups():
    assert group_by(read_table("k,v\n"), "k", "v") == {}


def test_errors(table):
    with pytest.raises(ValueError):
        group_by(table, "dept", "salary", "median")
    with pytest.raises(ValueError):
        group_by(table, "nope", "nope", "median")
    with pytest.raises(KeyError):
        group_by(table, "nope", "salary")
    with pytest.raises(KeyError):
        group_by(table, "dept", "nope")
    with pytest.raises(ValueError):
        group_by(table, "salary", "name")
    with pytest.raises(ValueError):
        group_by(table, "dept", "dept", "sum")
