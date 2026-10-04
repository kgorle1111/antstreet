from multisort import sort_records


def test_no_records():
    assert sort_records([], ["a", "-b"]) == []
    assert sort_records([], []) == []


def test_no_keys_keeps_the_input_order():
    rows = [{"id": 3, "v": 1}, {"id": 1, "v": 9}, {"id": 2}]
    assert sort_records(rows, []) == rows


def test_one_record():
    rows = [{"id": 1}]
    assert sort_records(rows, ["id", "-x"]) == rows


def test_empty_dicts_are_records_that_miss_every_field():
    rows = [{}, {"v": 1}, {}]
    out = sort_records(rows, ["v"])
    assert out == [{"v": 1}, {}, {}]
    assert out[1] is rows[0] and out[2] is rows[2]
