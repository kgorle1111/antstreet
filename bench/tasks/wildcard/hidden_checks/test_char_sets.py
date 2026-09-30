from wildcard import match


def test_set_matches_exactly_one_listed_character():
    assert match("[abc]", "a")
    assert match("[abc]", "c")
    assert not match("[abc]", "d")
    assert not match("[abc]", "")
    assert not match("[abc]", "ab")
    assert not match("[abc]", "A")


def test_set_inside_a_word():
    assert match("gr[ae]y", "grey")
    assert match("gr[ae]y", "gray")
    assert not match("gr[ae]y", "griy")
    assert not match("gr[ae]y", "gry")
    assert match("*[0-9]", "abc7")
    assert not match("*[0-9]", "abc")
    assert match("file[0-9].txt", "file4.txt")
    assert not match("file[0-9].txt", "file45.txt")


def test_ranges_include_both_ends():
    assert match("[a-c]", "a")
    assert match("[a-c]", "b")
    assert match("[a-c]", "c")
    assert not match("[a-c]", "d")
    assert match("[a-a]", "a")
    assert not match("[a-a]", "b")


def test_ranges_are_case_sensitive_and_by_code_point():
    assert match("[a-z]", "m")
    assert not match("[a-z]", "M")
    assert not match("[a-z]", "5")
    assert match("[A-z]", "_")
    assert match("[A-z]", "[")
    assert not match("[A-Z]", "_")


def test_several_ranges_and_characters_in_one_set():
    assert match("[a-cx-z]", "y")
    assert not match("[a-cx-z]", "m")
    assert match("[a-c0-9_]", "_")
    assert match("[a-c0-9_]", "7")
    assert not match("[a-c0-9_]", "-")


def test_reversed_range_matches_nothing():
    for char in "azm-":
        assert not match("[z-a]", char)
    assert match("[!z-a]", "m")


def test_negated_sets():
    assert match("[!abc]", "d")
    assert not match("[!abc]", "a")
    assert not match("[!abc]", "")
    assert not match("[!abc]", "dd")
    assert match("[!a-z]", "5")
    assert match("[!a-z]", "Q")
    assert not match("[!a-z]", "q")
    assert match("x[!0-9]y", "xay")
    assert not match("x[!0-9]y", "x5y")


def test_hyphen_first_or_last_is_an_ordinary_member():
    assert match("[a-]", "a")
    assert match("[a-]", "-")
    assert not match("[a-]", "b")
    assert match("[-a]", "-")
    assert match("[-a]", "a")
    assert not match("[-a]", "b")
    assert match("[!-a]", "b")
    assert not match("[!-a]", "-")
    assert not match("[!-a]", "a")
    assert match("[a-c-]", "-")


def test_bang_and_caret_are_only_special_where_stated():
    assert match("[a!]", "!")
    assert match("[a!]", "a")
    assert not match("[a!]", "b")
    assert match("[!!]", "x")
    assert not match("[!!]", "!")
    assert match("[^a]", "^")
    assert match("[^a]", "a")
    assert not match("[^a]", "b")


def test_wildcard_characters_inside_a_set_are_ordinary():
    for char in "*?[":
        assert match("[*?[]", char)
    assert not match("[*?[]", "a")
    assert not match("[*?[]", "")
    assert match("[a*]b", "*b")
    assert not match("[a*]b", "xb")


def test_set_combined_with_star_and_question_mark():
    assert match("[ab]*[cd]", "aXXd")
    assert match("[ab]*[cd]", "bc")
    assert not match("[ab]*[cd]", "cXXa")
    assert match("?[a-c]?", "xbz")
    assert not match("?[a-c]?", "xdz")


def test_non_ascii_members():
    assert match("[éè]", "è")
    assert not match("[éè]", "e")
    assert match("[!a]", "é")
