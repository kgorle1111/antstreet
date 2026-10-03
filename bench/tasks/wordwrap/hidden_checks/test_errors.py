import pytest
from wordwrap import wrap


@pytest.mark.parametrize("width", [0, -1, -10])
def test_width_below_one_raises(width):
    with pytest.raises(ValueError):
        wrap("some text", width)


@pytest.mark.parametrize("width", [None, "10", 10.0, 2.5, [10]])
def test_width_that_is_not_an_int_raises(width):
    with pytest.raises(ValueError):
        wrap("some text", width)


@pytest.mark.parametrize(
    ("width", "first", "rest"),
    [(4, "    ", ""), (4, "", "    "), (3, "    ", "  "), (5, "   ", "     "), (2, "\t\t", "")],
)
def test_an_indent_that_leaves_no_room_raises(width, first, rest):
    with pytest.raises(ValueError):
        wrap("some text", width, first_indent=first, rest_indent=rest)


def test_an_indent_that_leaves_exactly_one_character_is_allowed():
    assert wrap("abc", 3, first_indent="  ", rest_indent="  ") == ["  a", "  b", "  c"]


@pytest.mark.parametrize("text", [None, 5, b"abc", ["a", "b"]])
def test_text_that_is_not_a_string_raises(text):
    with pytest.raises(ValueError):
        wrap(text, 10)


@pytest.mark.parametrize(
    "kwargs", [{"first_indent": None}, {"rest_indent": 2}, {"first_indent": b" "}]
)
def test_an_indent_that_is_not_a_string_raises(kwargs):
    with pytest.raises(ValueError):
        wrap("some text", 10, **kwargs)


def test_arguments_are_checked_even_when_there_are_no_words():
    with pytest.raises(ValueError):
        wrap("", 0)
    with pytest.raises(ValueError):
        wrap("   ", 3, first_indent="   ")
