from wildcard import match


def test_escaped_star_is_literal():
    assert match("\\*", "*")
    assert not match("\\*", "a")
    assert not match("\\*", "")
    assert not match("\\*", "**")
    assert match("a\\*b", "a*b")
    assert not match("a\\*b", "axb")
    assert not match("a\\*b", "ab")


def test_escaped_question_mark_is_literal():
    assert match("\\?", "?")
    assert not match("\\?", "a")
    assert match("a\\?", "a?")
    assert not match("a\\?", "ab")


def test_escaped_open_bracket_is_literal_not_a_set():
    assert match("\\[abc]", "[abc]")
    assert not match("\\[abc]", "a")
    assert match("\\[", "[")
    assert match("a\\[b", "a[b")


def test_escaped_backslash_is_a_single_backslash():
    assert match("\\\\", "\\")
    assert not match("\\\\", "\\\\")
    assert not match("\\\\", "")
    assert match("a\\\\", "a\\")
    assert match("\\\\*", "\\anything")
    assert not match("\\\\*", "anything")


def test_backslash_before_an_ordinary_character_means_that_character():
    assert match("\\a", "a")
    assert not match("\\a", "\\a")
    assert match("\\-", "-")
    assert match("\\!", "!")
    assert match("\\]", "]")
    assert match("a\\bc", "abc")


def test_escapes_mix_with_wildcards():
    assert match("*\\*", "abc*")
    assert not match("*\\*", "abc")
    assert match("\\**", "*abc")
    assert match("\\*\\?[a-c]", "*?b")
    assert match("\\**\\*", "*mid*")


def test_escaped_closing_bracket_inside_a_set_is_a_member():
    assert match("[\\]]", "]")
    assert not match("[\\]]", "a")
    assert match("[\\]a]", "]")
    assert match("[\\]a]", "a")
    assert not match("[\\]a]", "b")
    assert match("[a\\]]", "]")
    assert match("[!\\]]", "a")
    assert not match("[!\\]]", "]")


def test_escaped_hyphen_inside_a_set_is_never_a_range():
    assert match("[a\\-z]", "a")
    assert match("[a\\-z]", "-")
    assert match("[a\\-z]", "z")
    assert not match("[a\\-z]", "b")
    assert not match("[a\\-z]", "m")


def test_escaped_bang_after_open_bracket_is_a_member():
    assert match("[\\!a]", "!")
    assert match("[\\!a]", "a")
    assert not match("[\\!a]", "b")


def test_escaped_backslash_inside_a_set():
    assert match("[\\\\]", "\\")
    assert not match("[\\\\]", "a")
    assert match("[\\\\a]", "a")


def test_escaped_range_ends():
    assert match("[\\]-a]", "^")
    assert not match("[\\]-a]", "b")
