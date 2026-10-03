from multisort import sort_records

ROWS = [
    {"id": 1, "dept": "ops", "salary": 50, "age": 30},
    {"id": 2, "dept": "dev", "salary": 70, "age": 41},
    {"id": 3, "dept": "dev", "salary": 90, "age": 28},
    {"id": 4, "dept": "ops", "salary": 50, "age": 25},
    {"id": 5, "dept": "dev", "salary": 70, "age": 35},
    {"id": 6, "dept": "ops", "salary": 80, "age": 52},
]


def ids(rows):
    return [r["id"] for r in rows]


def test_department_then_highest_salary_first():
    assert ids(sort_records(ROWS, ["dept", "-salary"])) == [3, 2, 5, 6, 1, 4]


def test_earlier_keys_matter_more():
    assert ids(sort_records(ROWS, ["salary", "dept"])) == [1, 4, 2, 5, 6, 3]
    assert ids(sort_records(ROWS, ["dept", "salary"])) == [2, 5, 3, 1, 4, 6]
    assert ids(sort_records(ROWS, ["-salary", "age"])) == [3, 6, 5, 2, 4, 1]


def test_three_keys_with_mixed_directions():
    assert ids(sort_records(ROWS, ["dept", "-salary", "age"])) == [3, 5, 2, 6, 4, 1]
    assert ids(sort_records(ROWS, ["-dept", "salary", "-age"])) == [1, 4, 6, 2, 5, 3]
    assert ids(sort_records(ROWS, ["-dept", "-salary", "-age"])) == [6, 1, 4, 3, 2, 5]


def test_a_repeated_key_changes_nothing():
    assert ids(sort_records(ROWS, ["dept", "dept", "-salary"])) == [3, 2, 5, 6, 1, 4]
    assert ids(sort_records(ROWS, ["salary", "-salary"])) == ids(sort_records(ROWS, ["salary"]))


def test_a_key_that_resolves_everything_makes_later_keys_irrelevant():
    assert ids(sort_records(ROWS, ["id", "-dept"])) == [1, 2, 3, 4, 5, 6]
    assert ids(sort_records(ROWS, ["-id", "dept"])) == [6, 5, 4, 3, 2, 1]
