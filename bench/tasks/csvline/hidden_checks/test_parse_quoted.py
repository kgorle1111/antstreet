import pytest
from csvline import parse_line


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('"abc"', ["abc"]),
        ('"a,b",c', ["a,b", "c"]),
        ('a,"b,c",d', ["a", "b,c", "d"]),
        ('"a,b,c"', ["a,b,c"]),
        ('"",""', ["", ""]),
        ('""', [""]),
        ('a,""', ["a", ""]),
        ('"",a', ["", "a"]),
    ],
)
def test_quoted_fields(line, expected):
    assert parse_line(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('"say ""hi"""', ['say "hi"']),
        ('""""', ['"']),
        ('"a""b"', ['a"b']),
        ('"""a"""', ['"a"']),
        ('"x""",y', ['x"', "y"]),
        ('"""",""""', ['"', '"']),
    ],
)
def test_doubled_quotes_are_one_quote(line, expected):
    assert parse_line(line) == expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('"a\nb"', ["a\nb"]),
        ('"a\r\nb",c', ["a\r\nb", "c"]),
        ('"a\rb"', ["a\rb"]),
        ('x,"\n",y', ["x", "\n", "y"]),
        ('"line one\nline, two\n""three"""', ['line one\nline, two\n"three"']),
    ],
)
def test_line_breaks_inside_quotes_are_kept_exactly(line, expected):
    assert parse_line(line) == expected
