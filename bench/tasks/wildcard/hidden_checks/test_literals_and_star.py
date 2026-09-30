import pytest
from wildcard import match


def test_literals_must_match_the_whole_text():
    assert match("abc", "abc")
    assert not match("abc", "abd")
    assert not match("abc", "ab")
    assert not match("ab", "abc")
    assert not match("abc", "xabc")


def test_empty_pattern_and_empty_text():
    assert match("", "")
    assert not match("", "a")
    assert not match("a", "")


def test_star_matches_any_run_including_none():
    assert match("*", "")
    assert match("*", "anything at all")
    assert match("**", "")
    assert match("***a***", "a")
    assert not match("***a***", "b")


def test_star_at_the_start_the_end_and_the_middle():
    assert match("ab*", "ab")
    assert match("ab*", "abcdef")
    assert not match("ab*", "a")
    assert match("*ab", "ab")
    assert match("*ab", "xxab")
    assert not match("*ab", "xabx")
    assert match("a*c", "ac")
    assert match("a*c", "abbbc")
    assert not match("a*c", "ab")
    assert not match("a*c", "bc")


def test_several_stars():
    assert match("a*b*c", "abc")
    assert match("a*b*c", "aXbYc")
    assert match("a*b*c", "abcbc")
    assert not match("a*b*c", "acb")
    assert match("*a*b*", "xxaxxbxx")
    assert not match("*a*b*", "xxbxxaxx")


@pytest.mark.parametrize(
    ("pattern", "text", "expected"),
    [
        ("*ab", "aab", True),
        ("*ab", "abab", True),
        ("*abc", "xabxabc", True),
        ("*abc", "xabxab", False),
        ("a*ab", "aab", True),
        ("a*ab", "ab", False),
        ("*ab*ab", "abab", True),
        ("*ab*ab", "aba", False),
        ("*aab", "aaab", True),
        ("*aab", "aabab", False),
        ("a*a*a", "aa", False),
        ("a*a*a", "aaa", True),
        ("*a*a*a*", "xaxaxax", True),
        ("*a*a*a*", "xaxax", False),
    ],
)
def test_star_must_be_able_to_give_characters_back(pattern, text, expected):
    assert match(pattern, text) is expected


def test_star_matches_every_kind_of_character():
    assert match("*", "a/b/c")
    assert match("*", ".hidden")
    assert match("a*z", "a\nz")
    assert match("*", "line1\nline2")
    assert match("*", "   ")
    assert match("a*z", "a/b.c z")


def test_matching_is_case_sensitive():
    assert not match("abc", "ABC")
    assert not match("A*", "abc")
    assert match("A*", "Abc")
    assert not match("*.PY", "x.py")


def test_other_regex_and_shell_characters_are_ordinary():
    assert match("a.c", "a.c")
    assert not match("a.c", "abc")
    assert match("(a|b)+", "(a|b)+")
    assert not match("a+", "aa")
    assert match("^a$", "^a$")
    assert match("a{2}", "a{2}")
    assert match("~/x", "~/x")
    assert match("a b", "a b")


def test_non_ascii_text():
    assert match("café", "café")
    assert match("é*", "école")
    assert not match("e*", "école")
