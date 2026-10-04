from multisort import sort_records


def ids(rows):
    return [r["id"] for r in rows]


ROWS = [
    {"id": 1, "v": 3},
    {"id": 2},
    {"id": 3, "v": 1},
    {"id": 4, "v": None},
    {"id": 5, "v": 2},
    {"id": 6},
]


def test_missing_values_come_last_ascending():
    assert ids(sort_records(ROWS, ["v"])) == [3, 5, 1, 2, 4, 6]


def test_missing_values_come_last_descending_too():
    assert ids(sort_records(ROWS, ["-v"])) == [1, 5, 3, 2, 4, 6]


def test_none_and_an_absent_key_are_the_same_and_keep_input_order():
    rows = [{"id": 1, "v": None}, {"id": 2}, {"id": 3, "v": None}, {"id": 4}]
    assert ids(sort_records(rows, ["v"])) == [1, 2, 3, 4]
    assert ids(sort_records(rows, ["-v"])) == [1, 2, 3, 4]


def test_zero_empty_string_and_false_are_values_not_missing():
    rows = [{"id": 1, "v": None}, {"id": 2, "v": 0}, {"id": 3, "v": -1}]
    assert ids(sort_records(rows, ["v"])) == [3, 2, 1]
    rows = [{"id": 1}, {"id": 2, "v": ""}, {"id": 3, "v": "a"}]
    assert ids(sort_records(rows, ["v"])) == [2, 3, 1]
    assert ids(sort_records(rows, ["-v"])) == [3, 2, 1]
    rows = [{"id": 1}, {"id": 2, "v": False}, {"id": 3, "v": True}]
    assert ids(sort_records(rows, ["-v"])) == [3, 2, 1]


def test_a_later_key_orders_the_records_that_are_missing_an_earlier_one():
    rows = [
        {"id": 1, "a": None, "b": 2},
        {"id": 2, "a": 5, "b": 9},
        {"id": 3, "b": 1},
        {"id": 4, "a": 5, "b": 3},
        {"id": 5, "a": 1},
    ]
    assert ids(sort_records(rows, ["a", "b"])) == [5, 4, 2, 3, 1]
    assert ids(sort_records(rows, ["-a", "-b"])) == [2, 4, 5, 1, 3]


def test_records_missing_the_second_key_come_last_inside_each_group():
    rows = [
        {"id": 1, "a": 1},
        {"id": 2, "a": 1, "b": 7},
        {"id": 3, "a": 0, "b": 4},
        {"id": 4, "a": 0},
        {"id": 5, "a": 1, "b": 2},
    ]
    assert ids(sort_records(rows, ["a", "b"])) == [3, 4, 5, 2, 1]
    assert ids(sort_records(rows, ["a", "-b"])) == [3, 4, 2, 5, 1]


def test_every_record_missing_the_field_keeps_input_order():
    rows = [{"id": 3}, {"id": 1}, {"id": 2}]
    assert ids(sort_records(rows, ["v"])) == [3, 1, 2]
