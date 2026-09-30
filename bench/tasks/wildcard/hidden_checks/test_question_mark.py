from wildcard import match


def test_question_mark_matches_exactly_one_character():
    assert match("?", "a")
    assert not match("?", "")
    assert not match("?", "ab")


def test_question_mark_inside_literals():
    assert match("a?c", "abc")
    assert match("a?c", "a-c")
    assert not match("a?c", "ac")
    assert not match("a?c", "abbc")
    assert match("?.txt", "a.txt")
    assert not match("?.txt", ".txt")


def test_several_question_marks_count_characters():
    assert match("???", "abc")
    assert not match("??", "abc")
    assert not match("????", "abc")
    assert match("??.py", "ab.py")
    assert not match("??.py", "abc.py")


def test_question_mark_matches_any_kind_of_character():
    assert match("?", "\n")
    assert match("?", "/")
    assert match("?", ".")
    assert match("?", "*")
    assert match("?", "?")
    assert match("?", "[")


def test_question_mark_counts_characters_not_bytes():
    assert match("?", "é")
    assert match("caf?", "café")
    assert match("?", "\U0001f600")
    assert not match("??", "é")


def test_question_mark_with_star():
    assert not match("?*", "")
    assert match("?*", "a")
    assert match("?*", "abc")
    assert not match("*?", "")
    assert match("*?", "abc")
    assert match("*?*?*", "ab")
    assert not match("*?*?*", "a")
    assert match("a*?", "ab")
    assert not match("a*?", "a")
    assert match("?*?", "ab")
    assert not match("?*?", "a")


def test_a_question_mark_in_the_pattern_is_not_a_literal():
    assert match("a?", "ab")
    assert match("a?", "a?")
    assert not match("a?", "a")
