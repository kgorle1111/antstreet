from editdistance import edit_distance, edit_script


def test_comparison_is_case_sensitive():
    assert edit_distance("A", "a") == 1
    assert edit_script("Ab", "ab") == [("sub", "A", "a"), ("keep", "b")]
    assert edit_distance("ABC", "abc") == 3


def test_non_ascii_and_astral_characters_count_once_each():
    assert edit_distance("café", "cafe") == 1
    assert edit_script("café", "cafe") == [
        ("keep", "c"),
        ("keep", "a"),
        ("keep", "f"),
        ("sub", "é", "e"),
    ]
    assert edit_distance("😀😀", "😀") == 1
    assert edit_script("a😀", "😀b") == [("sub", "a", "😀"), ("sub", "😀", "b")]


def test_whitespace_and_digits_are_ordinary_characters():
    assert edit_distance("a b", "ab") == 1
    assert edit_script("a b", "ab") == [("keep", "a"), ("delete", " "), ("keep", "b")]
    assert edit_distance("123", "132") == 2
