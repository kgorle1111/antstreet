import pytest
from iniparse import parse_ini


@pytest.mark.parametrize("text", ["[a", "[a]x", "[", "[a] ; note", "[a]]x", "[ab\nk=v"])
def test_header_must_end_with_a_closing_bracket(text):
    with pytest.raises(ValueError):
        parse_ini(text)


@pytest.mark.parametrize("text", ["[]", "[ ]", "[\t]", "[s]\n[]"])
def test_empty_section_name_is_an_error(text):
    with pytest.raises(ValueError):
        parse_ini(text)


@pytest.mark.parametrize("text", ["novalue", "[s]\njust a line", "[s]\nk : v", "[s]\nk\nj=1", "]"])
def test_a_line_without_equals_is_an_error(text):
    with pytest.raises(ValueError):
        parse_ini(text)


@pytest.mark.parametrize("text", ["= v", "[s]\n=", "[s]\n  = v", "[s]\nk=1\n=2"])
def test_an_empty_key_is_an_error(text):
    with pytest.raises(ValueError):
        parse_ini(text)


@pytest.mark.parametrize("bad", [None, 1, 2.5, b"[a]\nk=v", ["[a]"], {"a": "b"}])
def test_non_string_argument_raises_value_error(bad):
    with pytest.raises(ValueError):
        parse_ini(bad)


def test_an_error_late_in_the_text_still_raises():
    with pytest.raises(ValueError):
        parse_ini("[a]\n" + "k = v\n" * 50 + "oops\n")
