import pytest
from multisort import sort_records

ROWS = [{"k": 1}, {"k": 2}]


@pytest.mark.parametrize("spec", ["", "-"])
def test_a_spec_without_a_field_name_is_a_value_error(spec):
    with pytest.raises(ValueError):
        sort_records(ROWS, [spec])
    with pytest.raises(ValueError):
        sort_records(ROWS, ["k", spec])
    with pytest.raises(ValueError):
        sort_records([], [spec])


@pytest.mark.parametrize("spec", [None, 5, b"k", ("k",), 1.5, ["k"]])
def test_a_spec_that_is_not_a_str_is_a_type_error(spec):
    with pytest.raises(TypeError):
        sort_records(ROWS, [spec])
    with pytest.raises(TypeError):
        sort_records([], ["k", spec])


@pytest.mark.parametrize("bad", [None, "k", {"k": 1}, 5, {1, 2}])
def test_records_and_keys_must_be_lists(bad):
    with pytest.raises(TypeError):
        sort_records(bad, ["k"])
    with pytest.raises(TypeError):
        sort_records(ROWS, bad)


@pytest.mark.parametrize("record", [None, 5, "k", ["k"], ("k", 1)])
def test_a_record_that_is_not_a_dict_is_a_type_error(record):
    with pytest.raises(TypeError):
        sort_records([{"k": 1}, record], ["k"])
    with pytest.raises(TypeError):
        sort_records([record], [])
    with pytest.raises(TypeError):
        sort_records([record], ["missing"])


def test_key_specs_are_checked_before_the_records():
    with pytest.raises(ValueError):
        sort_records([5], [""])
    with pytest.raises(TypeError):
        sort_records([5], [None])
    with pytest.raises(ValueError):
        sort_records([{"k": 1}, 5], ["k", "-"])
