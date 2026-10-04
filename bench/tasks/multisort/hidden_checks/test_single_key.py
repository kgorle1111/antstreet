from multisort import sort_records


def names(rows):
    return [r["n"] for r in rows]


def test_ascending_and_descending_numbers():
    rows = [{"n": "a", "v": 3}, {"n": "b", "v": 1}, {"n": "c", "v": 2}]
    assert names(sort_records(rows, ["v"])) == ["b", "c", "a"]
    assert names(sort_records(rows, ["-v"])) == ["a", "c", "b"]


def test_strings_compare_as_python_strings():
    rows = [{"n": 1, "s": "pear"}, {"n": 2, "s": "Apple"}, {"n": 3, "s": "apple"}]
    assert names(sort_records(rows, ["s"])) == [2, 3, 1]
    assert names(sort_records(rows, ["-s"])) == [1, 3, 2]


def test_negative_numbers_floats_and_bools():
    rows = [{"n": 1, "v": -2.5}, {"n": 2, "v": 0}, {"n": 3, "v": -10}, {"n": 4, "v": 3.5}]
    assert names(sort_records(rows, ["v"])) == [3, 1, 2, 4]
    assert names(sort_records(rows, ["-v"])) == [4, 2, 1, 3]
    flags = [{"n": 1, "v": True}, {"n": 2, "v": False}]
    assert names(sort_records(flags, ["v"])) == [2, 1]


def test_other_fields_are_ignored_and_records_keep_their_content():
    rows = [{"n": "x", "v": 2, "extra": [1]}, {"n": "y", "v": 1}]
    out = sort_records(rows, ["v"])
    assert out == [{"n": "y", "v": 1}, {"n": "x", "v": 2, "extra": [1]}]


def test_a_dash_inside_or_doubled_in_a_field_name():
    rows = [{"n": 1, "a-b": 2, "-x": 5}, {"n": 2, "a-b": 1, "-x": 9}]
    assert names(sort_records(rows, ["a-b"])) == [2, 1]
    assert names(sort_records(rows, ["-a-b"])) == [1, 2]
    assert names(sort_records(rows, ["--x"])) == [2, 1]
    assert names(sort_records(rows, ["-n"])) == [2, 1]
