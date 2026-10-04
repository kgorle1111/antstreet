from editdistance import edit_distance, edit_script


def test_two_empty_strings():
    assert edit_distance("", "") == 0
    assert edit_script("", "") == []


def test_one_empty_string_is_all_inserts_or_all_deletes():
    assert edit_script("", "abc") == [("insert", "a"), ("insert", "b"), ("insert", "c")]
    assert edit_script("xy", "") == [("delete", "x"), ("delete", "y")]


def test_a_single_character_against_nothing():
    assert edit_script("", "z") == [("insert", "z")]
    assert edit_script("z", "") == [("delete", "z")]
    assert edit_distance("z", "") == 1
