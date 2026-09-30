import pytest
from csvline import parse_line


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("a,b,c", ["a", "b", "c"]),
        ("hello", ["hello"]),
        ("one two,three", ["one two", "three"]),
        ("1,2.5,-3", ["1", "2.5", "-3"]),
    ],
)
def test_plain_fields(line, expected):
    assert parse_line(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("", [""]),
        (",", ["", ""]),
        (",,", ["", "", ""]),
        ("a,,b", ["a", "", "b"]),
        ("a,", ["a", ""]),
        (",a", ["", "a"]),
    ],
)
def test_empty_fields(line, expected):
    assert parse_line(line) == expected
