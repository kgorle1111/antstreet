import pytest
from wildcard import filter_names, match

UNCLOSED_SETS = ["[", "[abc", "[!abc", "[]", "[!]", "[!", "a[", "[a-", "[a-z", "[]a", "x[]y", "*["]
LONE_BACKSLASHES = ["\\", "abc\\", "*\\", "[a\\", "\\\\\\", "a\\\\\\", "?\\"]
UNCLOSED_WITH_ESCAPE = ["[\\]", "[a\\]", "[!\\]", "[\\]a"]


@pytest.mark.parametrize("pattern", UNCLOSED_SETS + UNCLOSED_WITH_ESCAPE)
def test_unclosed_set_raises_value_error(pattern):
    with pytest.raises(ValueError):
        match(pattern, "abc")


@pytest.mark.parametrize("pattern", LONE_BACKSLASHES)
def test_trailing_lone_backslash_raises_value_error(pattern):
    with pytest.raises(ValueError):
        match(pattern, "abc")


@pytest.mark.parametrize("pattern", ["a[", "abc\\", "*[", "?[!", "\\"])
@pytest.mark.parametrize("text", ["", "z", "a very different text"])
def test_invalid_pattern_raises_even_when_the_text_cannot_match(pattern, text):
    with pytest.raises(ValueError):
        match(pattern, text)


def test_invalid_pattern_raises_even_after_a_failed_prefix():
    with pytest.raises(ValueError):
        match("abc[", "x")
    with pytest.raises(ValueError):
        match("[", "")
    with pytest.raises(ValueError):
        match("a\\", "zzz")
    with pytest.raises(ValueError):
        match("b*[", "abc")


def test_filter_names_raises_even_without_names():
    with pytest.raises(ValueError):
        filter_names("[", [])
    with pytest.raises(ValueError):
        filter_names("abc\\", [])
    with pytest.raises(ValueError):
        filter_names("[abc", ["abc", "x"])


def test_valid_look_alikes_do_not_raise():
    assert match("[]]", "]")
    assert match("[!]]", "a")
    assert match("\\[", "[")
    assert match("a]", "a]")
    assert match("\\\\", "\\")
    assert match("a\\\\", "a\\")
    assert match("[[]", "[")
    assert match("[a\\]]", "]")
    assert match("[*]", "*")
    assert match("]", "]")
    assert match("\\\\\\\\", "\\\\")
    assert filter_names("[]]", []) == []
