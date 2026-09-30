import pytest
from csvline import format_line


@pytest.mark.parametrize("bad", [None, 1, 2.5, True, b"abc", ["a"], ("a",), {"a": 1}])
def test_non_string_field_raises(bad):
    with pytest.raises(ValueError):
        format_line([bad])


@pytest.mark.parametrize("position", [0, 1, 2])
def test_non_string_field_raises_wherever_it_appears(position):
    fields = ["a", "b", "c"]
    fields[position] = None
    with pytest.raises(ValueError):
        format_line(fields)


def test_empty_list_raises():
    with pytest.raises(ValueError):
        format_line([])
