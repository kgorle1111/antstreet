import pytest
from csvline import parse_line


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (" a , b ", [" a ", " b "]),
        ("  ", ["  "]),
        ("a, ,b", ["a", " ", "b"]),
        ("\ta\t,b", ["\ta\t", "b"]),
        ("a b  c", ["a b  c"]),
    ],
)
def test_unquoted_whitespace_is_preserved(line, expected):
    assert parse_line(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('" a "', [" a "]),
        ('"  ",b', ["  ", "b"]),
        ('"\ta",b', ["\ta", "b"]),
        ('a," b ",c', ["a", " b ", "c"]),
    ],
)
def test_quoted_whitespace_is_preserved(line, expected):
    assert parse_line(line) == expected
