import pytest
from wordwrap import wrap


@pytest.mark.parametrize("text", ["", " ", "   ", "\n", "\t \n\r\n ", " "])
def test_text_without_words_gives_an_empty_list(text):
    assert wrap(text, 10) == []


def test_runs_of_whitespace_collapse_to_one_space():
    assert wrap("a    b \t c", 20) == ["a b c"]


def test_newlines_are_ordinary_whitespace():
    assert wrap("one\ntwo\n\nthree", 20) == ["one two three"]
    assert wrap("one\r\ntwo", 20) == ["one two"]


def test_leading_and_trailing_whitespace_is_dropped():
    assert wrap("   a b   ", 20) == ["a b"]
    assert wrap("\n\n  a  \n\n", 3) == ["a"]


def test_no_line_starts_or_ends_with_a_space():
    lines = wrap("  aa   bb  cc   dd ee  ff   ", 6)
    assert lines == ["aa bb", "cc dd", "ee ff"]
    assert all(line == line.strip() and line for line in lines)


def test_whitespace_collapsing_does_not_change_where_lines_break():
    spaced = wrap("aa     bb     cc", 5)
    assert spaced == wrap("aa bb cc", 5) == ["aa bb", "cc"]
