from undoredo import TextBuffer


def test_the_first_insert_after_an_undo_starts_a_new_step():
    b = TextBuffer()
    b.insert(0, "ab", now=0.0)
    b.insert(2, "c", now=100.0)
    assert b.undo() is True
    assert b.text == "ab"
    b.insert(2, "d", now=100.5)
    assert b.text == "abd"
    b.undo()
    assert b.text == "ab"
    b.undo()
    assert b.text == ""


def test_the_first_insert_after_a_redo_starts_a_new_step():
    b = TextBuffer()
    b.insert(0, "ab", now=0.0)
    b.insert(2, "c", now=100.0)
    b.undo()
    b.redo()
    assert b.text == "abc"
    b.insert(3, "d", now=100.5)
    assert b.text == "abcd"
    b.undo()
    assert b.text == "abc"
    b.undo()
    assert b.text == "ab"


def test_typing_after_the_new_step_merges_into_it_again():
    b = TextBuffer()
    b.insert(0, "ab", now=0.0)
    b.insert(2, "c", now=100.0)
    b.undo()
    b.insert(2, "d", now=100.2)
    b.insert(3, "e", now=100.4)
    assert b.text == "abde"
    b.undo()
    assert b.text == "ab"


def test_typing_with_no_undo_in_between_still_merges():
    b = TextBuffer()
    b.insert(0, "a", now=0.0)
    b.insert(1, "b", now=0.2)
    b.undo()
    assert b.text == ""
    assert b.can_undo is False
