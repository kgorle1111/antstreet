import dataclasses
import math

import pytest
from reader import read_table
from stats import Summary, describe


def test_basic_summary():
    s = describe([1, 2, 3, 4])
    assert s.count == 4
    assert s.missing == 0
    assert s.mean == 2.5
    assert s.minimum == 1
    assert s.maximum == 4
    assert s.median == 2.5
    assert s.stdev == pytest.approx(math.sqrt(5 / 3))


def test_median_of_odd_and_even_counts():
    assert describe([3, 1, 2]).median == 2.0
    assert describe([10, 1, 7, 3, 5]).median == 5.0
    assert describe([4, 1, 3, 2]).median == 2.5
    assert describe([1, 100]).median == 50.5


def test_stdev_is_the_sample_deviation():
    assert describe([100, 120, 80]).stdev == pytest.approx(20.0)
    assert describe([2, 4]).stdev == pytest.approx(math.sqrt(2))
    assert describe([5, 5, 5]).stdev == 0.0


def test_missing_values_are_counted_but_not_used():
    s = describe([None, 2, None, 4, None])
    assert (s.count, s.missing) == (2, 3)
    assert s.mean == 3.0
    assert (s.minimum, s.maximum, s.median) == (2.0, 4.0, 3.0)


def test_one_number_has_no_stdev():
    s = describe([7])
    assert (s.count, s.missing) == (1, 0)
    assert s.mean == s.minimum == s.maximum == s.median == 7.0
    assert s.stdev is None
    assert describe([None, 7.5]).stdev is None


def test_nothing_to_describe():
    assert describe([]) == Summary(0, 0, None, None, None, None, None)
    assert describe([None, None]) == Summary(0, 2, None, None, None, None, None)
    assert describe(iter([])).count == 0


def test_values_are_floats_whatever_goes_in():
    s = describe([1, 2, 3])
    for value in (s.mean, s.minimum, s.maximum, s.median, s.stdev):
        assert isinstance(value, float)
    assert isinstance(s.count, int) and isinstance(s.missing, int)


def test_any_iterable_negative_numbers_and_the_input_is_not_consumed_twice():
    s = describe(x for x in [-3, -1, 2, None])
    assert (s.count, s.missing) == (3, 1)
    assert s.minimum == -3.0 and s.maximum == 2.0 and s.median == -1.0
    assert s.mean == pytest.approx(-2 / 3)


def test_summary_is_a_frozen_value_with_these_fields():
    s = describe([1, 2])
    assert [f.name for f in dataclasses.fields(Summary)] == [
        "count",
        "missing",
        "mean",
        "minimum",
        "maximum",
        "median",
        "stdev",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.count = 5


def test_describe_on_a_parsed_column():
    table = read_table("salary,age\n100,30\n120,\n80,41\n,28\n")
    s = describe(table.numbers("salary"))
    assert (s.count, s.missing, s.mean, s.stdev) == (3, 1, 100.0, pytest.approx(20.0))
    a = describe(table.numbers("age"))
    assert (a.count, a.missing, a.median, a.stdev) == (3, 1, 30.0, pytest.approx(7.0))
