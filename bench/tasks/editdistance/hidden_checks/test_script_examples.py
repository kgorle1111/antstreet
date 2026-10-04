from editdistance import edit_script


def test_kitten_sitting():
    assert edit_script("kitten", "sitting") == [
        ("sub", "k", "s"),
        ("keep", "i"),
        ("keep", "t"),
        ("keep", "t"),
        ("sub", "e", "i"),
        ("keep", "n"),
        ("insert", "g"),
    ]


def test_identical_strings_are_all_keeps():
    assert edit_script("abc", "abc") == [("keep", "a"), ("keep", "b"), ("keep", "c")]


def test_one_substitution():
    assert edit_script("a", "b") == [("sub", "a", "b")]
    assert edit_script("cat", "cut") == [("keep", "c"), ("sub", "a", "u"), ("keep", "t")]


def test_one_deletion_in_the_middle_and_one_insertion():
    assert edit_script("abc", "ac") == [("keep", "a"), ("delete", "b"), ("keep", "c")]
    assert edit_script("ac", "abc") == [("keep", "a"), ("insert", "b"), ("keep", "c")]


def test_operations_are_tuples_of_strings():
    for op in edit_script("kitten", "sitting"):
        assert isinstance(op, tuple)
        assert all(isinstance(part, str) for part in op)
