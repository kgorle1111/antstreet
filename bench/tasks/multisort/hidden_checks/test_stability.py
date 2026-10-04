from multisort import sort_records


def ids(rows):
    return [r["id"] for r in rows]


ROWS = [
    {"id": 1, "k": 2},
    {"id": 2, "k": 1},
    {"id": 3, "k": 2},
    {"id": 4, "k": 1},
    {"id": 5, "k": 2},
]


def test_ties_keep_input_order_ascending():
    assert ids(sort_records(ROWS, ["k"])) == [2, 4, 1, 3, 5]


def test_ties_keep_input_order_descending():
    assert ids(sort_records(ROWS, ["-k"])) == [1, 3, 5, 2, 4]


def test_example_from_the_idea():
    rows = [{"k": 1, "n": "a"}, {"k": 1, "n": "b"}]
    assert [r["n"] for r in sort_records(rows, ["-k"])] == ["a", "b"]
    assert [r["n"] for r in sort_records(rows, ["k"])] == ["a", "b"]


def test_ties_on_every_key_keep_input_order_with_mixed_directions():
    rows = [{"id": i, "a": i % 2, "b": i % 3} for i in range(12)]
    out = sort_records(rows, ["-a", "b"])
    expected = sorted(rows, key=lambda r: (-r["a"], r["b"]))  # sorted() is stable
    assert ids(out) == ids(expected)


def test_the_input_order_is_the_tie_break_not_the_value_of_other_fields():
    rows = [{"id": 9, "k": 1}, {"id": 3, "k": 1}, {"id": 5, "k": 1}]
    assert ids(sort_records(rows, ["k"])) == [9, 3, 5]
    assert ids(sort_records(rows, ["-k"])) == [9, 3, 5]
    assert ids(sort_records(rows, ["nope"])) == [9, 3, 5]
