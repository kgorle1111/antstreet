import pytest
from iniparse import parse_ini


@pytest.mark.parametrize(
    ("line", "key", "value"),
    [
        ("k=v", "k", "v"),
        ("k = v", "k", "v"),
        ("  k  =  v  ", "k", "v"),
        ("\tk\t=\tv\t", "k", "v"),
        ("k =", "k", ""),
        ("k=", "k", ""),
        ("k =    ", "k", ""),
        ("url = a=b", "url", "a=b"),
        ("eq = ==", "eq", "=="),
        ("two words = three  words here", "two words", "three  words here"),
        ("path = C:\\temp\\x", "path", "C:\\temp\\x"),
    ],
)
def test_split_at_the_first_equals_and_trim(line, key, value):
    assert parse_ini("[s]\n" + line) == {"s": {key: value}}


def test_keys_before_any_header_go_to_the_empty_section():
    assert parse_ini("a = 1\nb = 2\n[s]\nc = 3") == {"": {"a": "1", "b": "2"}, "s": {"c": "3"}}


def test_the_empty_section_is_absent_when_no_key_precedes_a_header():
    assert "" not in parse_ini("; c\n\n[s]\nk=v")
    assert "" not in parse_ini("")


def test_crlf_line_endings_leave_no_carriage_returns():
    assert parse_ini("[s]\r\nk = v\r\nj = 2\r\n") == {"s": {"k": "v", "j": "2"}}


def test_no_trailing_newline_is_needed():
    assert parse_ini("[s]\nk=v") == parse_ini("[s]\nk=v\n")
