import pytest
from iniparse import parse_ini


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ('"x"', "x"),
        ('"  x "', "  x "),
        ('""', ""),
        ('" "', " "),
        ('"a = b"', "a = b"),
        ('"a ; b"', "a ; b"),
        ('"say ""hi"""', 'say ""hi""'),
        ('"\\n"', "\\n"),
    ],
)
def test_surrounding_double_quotes_are_removed_and_the_inside_kept(raw, value):
    assert parse_ini(f"[s]\nk = {raw}") == {"s": {"k": value}}


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ('"', '"'),
        ('"abc', '"abc'),
        ('abc"', 'abc"'),
        ("'x'", "'x'"),
        ("'  x '", "'  x '"),
        ('a "b" c', 'a "b" c'),
        ('"a" b', '"a" b'),
    ],
)
def test_other_values_are_left_as_written(raw, value):
    assert parse_ini(f"[s]\nk = {raw}") == {"s": {"k": value}}


def test_whitespace_outside_the_quotes_is_still_trimmed():
    assert parse_ini('[s]\nk =   "  x "   ') == {"s": {"k": "  x "}}


def test_keys_are_not_unquoted():
    assert parse_ini('[s]\n"k" = v') == {"s": {'"k"': "v"}}
