import pytest
from httpheaders import parse_headers


def test_a_folded_value_is_joined_with_one_space():
    h = parse_headers("A: one\r\n  two\r\n\tthree\r\nB: x")
    assert h.items() == [("A", "one two three"), ("B", "x")]


@pytest.mark.parametrize(
    "text",
    [
        "A: one\r\n two",
        "A: one\r\n      two",
        "A: one\r\n\ttwo",
        "A: one\r\n \t two \t",
        "A: one  \r\n two",
        "A: one\n two",
        "A:one\n two",
    ],
)
def test_the_spacing_around_the_parts_does_not_matter(text):
    assert parse_headers(text).items() == [("A", "one two")]


def test_a_folded_header_counts_once():
    h = parse_headers("A: 1\r\n 2\r\n 3\r\nB: x\r\n y")
    assert len(h) == 2
    assert h.get_all("a") == ["1 2 3"]


def test_the_first_part_may_be_empty():
    assert parse_headers("A:\r\n  two").items() == [("A", "two")]
    assert parse_headers("A: \r\n\tone\r\n two").items() == [("A", "one two")]


def test_a_continuation_that_is_blank_after_stripping_adds_nothing():
    assert parse_headers("A: one\r\n  \r\n two").items() == [("A", "one two")]
    assert parse_headers("A: one\r\n \t \r\nB: x").items() == [("A", "one"), ("B", "x")]
    assert parse_headers("A:\r\n  \r\n  ").items() == [("A", "")]


def test_a_continuation_goes_with_the_header_just_above_it():
    h = parse_headers("A: 1\r\nB: 2\r\n 3\r\nA: 4\r\n 5")
    assert h.items() == [("A", "1"), ("B", "2 3"), ("A", "4 5")]
    assert h.get("a") == "1, 4 5"


def test_a_folded_line_with_colons_stays_part_of_the_value():
    h = parse_headers("A: one\r\n two: three\r\n  four:")
    assert h.items() == [("A", "one two: three four:")]


def test_the_inner_spaces_of_a_part_are_kept():
    assert parse_headers("A: a  b\r\n c   d").items() == [("A", "a  b c   d")]


def test_a_continuation_line_before_any_header_is_an_error():
    for text in (" x", "\tx", " x\r\nA: 1", "  : y", " "):
        with pytest.raises(ValueError):
            parse_headers(text)
