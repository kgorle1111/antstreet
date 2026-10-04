import copy

from multisort import sort_records


def test_the_input_list_and_its_dicts_are_not_changed():
    rows = [{"id": 1, "k": 3}, {"id": 2, "k": 1}, {"id": 3}, {"id": 4, "k": 2}]
    before = copy.deepcopy(rows)
    ids_before = [id(r) for r in rows]
    sort_records(rows, ["k"])
    sort_records(rows, ["-k", "id"])
    assert rows == before
    assert [id(r) for r in rows] == ids_before


def test_the_result_is_a_new_list_of_the_same_dict_objects():
    rows = [{"id": 1, "k": 3}, {"id": 2, "k": 1}]
    out = sort_records(rows, ["k"])
    assert out is not rows
    assert out[0] is rows[1] and out[1] is rows[0]
    out.append({"id": 3})
    assert len(rows) == 2


def test_with_no_keys_the_result_is_still_a_new_list():
    rows = [{"id": 2}, {"id": 1}]
    out = sort_records(rows, [])
    assert out == rows and out is not rows
    assert all(a is b for a, b in zip(out, rows, strict=True))


def test_a_tuple_of_records_and_of_keys_is_accepted():
    rows = ({"id": 2, "k": 2}, {"id": 1, "k": 1})
    out = sort_records(rows, ("k",))
    assert isinstance(out, list)
    assert [r["id"] for r in out] == [1, 2]


def test_the_keys_list_is_not_changed():
    keys = ["-a", "b"]
    sort_records([{"a": 1, "b": 2}, {"a": 2, "b": 1}], keys)
    assert keys == ["-a", "b"]
