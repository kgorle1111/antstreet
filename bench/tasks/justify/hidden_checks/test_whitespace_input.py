import pytest
from justify import justify


@pytest.mark.parametrize("text", ["", " ", "   ", "\n", "\t \n \t"])
def test_no_words_gives_empty_list(text):
    assert justify(text, 10) == []


def test_any_whitespace_separates_words():
    assert justify("a\tb\nc", 5) == ["a b c"]
    assert justify("a  \t\n  b", 3) == ["a b"]


def test_leading_and_trailing_whitespace_is_ignored():
    assert justify(" \t hello\n\nworld  \n", 11) == ["hello world"]
