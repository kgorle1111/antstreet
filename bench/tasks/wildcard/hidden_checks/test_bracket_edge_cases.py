from wildcard import match


def test_closing_bracket_right_after_open_is_a_member():
    assert match("[]]", "]")
    assert not match("[]]", "")
    assert not match("[]]", "a")
    assert not match("[]]", "]]")


def test_closing_bracket_first_with_other_members():
    assert match("[]a]", "]")
    assert match("[]a]", "a")
    assert not match("[]a]", "b")
    assert match("[a]]", "a]")
    assert not match("[a]]", "a")
    assert not match("[a]]", "]")


def test_closing_bracket_first_in_a_negated_set():
    assert match("[!]]", "a")
    assert not match("[!]]", "]")
    assert not match("[!]]", "")
    assert match("[!]a]", "b")
    assert not match("[!]a]", "]")
    assert not match("[!]a]", "a")


def test_the_first_closing_bracket_after_a_member_ends_the_set():
    assert match("[ab]]", "b]")
    assert not match("[ab]]", "b")
    assert match("[a-c]]", "b]")
    assert match("x[a]]y", "xa]y")


def test_closing_bracket_outside_a_set_is_ordinary():
    assert match("]", "]")
    assert not match("]", "a")
    assert match("a]", "a]")
    assert match("]]", "]]")
    assert match("*]", "abc]")
    assert not match("*]", "abc")


def test_open_bracket_inside_a_set_is_ordinary():
    assert match("[[]", "[")
    assert not match("[[]", "]")
    assert match("[[]]", "[]")
    assert not match("[[]]", "[")
    assert match("[[a]", "a")


def test_a_set_must_match_a_character_never_nothing():
    assert not match("a[bc]", "a")
    assert not match("[]]", "")
    assert not match("[!x]", "")
    assert match("a[bc]*", "ab")
    assert match("a[bc]*", "abzzz")
