import pytest
from csvline import format_line


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (["a", "b", "c"], "a,b,c"),
        (["hello"], "hello"),
        (["a b", "c  d"], "a b,c  d"),
        ([""], ""),
        (["", ""], ","),
        (["a", "", "b"], "a,,b"),
        (["x;y", "p'q", "1.5"], "x;y,p'q,1.5"),
    ],
)
def test_plain_fields_are_not_quoted(fields, expected):
    assert format_line(fields) == expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (["a,b"], '"a,b"'),
        (["a,b", "c"], '"a,b",c'),
        (["a\nb"], '"a\nb"'),
        (["a\rb"], '"a\rb"'),
        (["a\r\nb", "c"], '"a\r\nb",c'),
        (["\n"], '"\n"'),
    ],
)
def test_comma_or_line_break_forces_quotes(fields, expected):
    assert format_line(fields) == expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (['say "hi"'], '"say ""hi"""'),
        (['"'], '""""'),
        (['a"b', "c"], '"a""b",c'),
        (['""'], '""""""'),
        (['"a",b'], '"""a"",b"'),
    ],
)
def test_embedded_quotes_are_doubled_and_the_field_is_quoted(fields, expected):
    assert format_line(fields) == expected


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ([" a"], '" a"'),
        (["a "], '"a "'),
        ([" "], '" "'),
        (["\ta"], '"\ta"'),
        (["a\t"], '"a\t"'),
        ([" a ", "b"], '" a ",b'),
    ],
)
def test_leading_or_trailing_whitespace_forces_quotes(fields, expected):
    assert format_line(fields) == expected
