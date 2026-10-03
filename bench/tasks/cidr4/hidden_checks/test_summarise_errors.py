import pytest
from cidr4 import summarise


@pytest.mark.parametrize(
    "blocks",
    [
        ["10.0.0.1/24"],
        ["10.0.0.0/24", "10.0.0.1/24"],
        ["10.0.0.0"],
        ["10.0.0.0/33"],
        ["x"],
        [""],
        ["10.0.0.0/24", "300.0.0.0/8"],
        ["10.0.0.0/24", "10.0.0.0/08"],
        ["10.0.0.0/25", "10.0.0.128/25", "10.0.1.5/24"],
    ],
)
def test_an_invalid_item_raises_value_error(blocks):
    with pytest.raises(ValueError):
        summarise(blocks)


@pytest.mark.parametrize(
    "blocks",
    [
        None,
        "10.0.0.0/24",
        5,
        {"10.0.0.0/24"},
        iter(["10.0.0.0/24"]),
        b"10.0.0.0/24",
        {"10.0.0.0/24": 1},
    ],
)
def test_a_value_that_is_not_a_list_or_tuple_raises_type_error(blocks):
    with pytest.raises(TypeError):
        summarise(blocks)


@pytest.mark.parametrize("blocks", [[None], [5], [b"10.0.0.0/24"], ["10.0.0.0/24", None]])
def test_an_item_that_is_not_a_str_raises_type_error(blocks):
    with pytest.raises(TypeError):
        summarise(blocks)


def test_a_tuple_works_like_a_list():
    assert summarise(("10.0.0.0/25", "10.0.0.128/25")) == ["10.0.0.0/24"]
    assert summarise(()) == []
