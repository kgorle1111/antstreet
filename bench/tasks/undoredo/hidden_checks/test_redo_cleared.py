from undoredo import TextBuffer


def test_an_insert_after_undo_discards_the_redo_history():
    b = TextBuffer("abc")
    b.insert(3, "d", now=0)
    b.undo()
    assert b.can_redo is True
    b.insert(0, "X", now=10)
    assert b.can_redo is False
    assert b.redo() is False
    assert b.text == "Xabc"


def test_a_delete_after_undo_discards_the_redo_history():
    b = TextBuffer("abc")
    b.insert(3, "d", now=0)
    b.undo()
    b.delete(0, 1, now=10)
    assert b.can_redo is False
    assert b.text == "bc"


def test_all_undone_steps_are_lost_not_just_the_last_one():
    b = TextBuffer()
    for i, ch in enumerate("abc"):
        b.insert(0, ch, now=10 * i)
    b.undo()
    b.undo()
    b.insert(0, "Z", now=100)
    assert b.can_redo is False
    assert b.undo() is True
    assert b.undo() is True
    assert b.undo() is False
    assert b.text == ""


def test_undo_after_the_new_edit_goes_back_through_the_old_history():
    b = TextBuffer("")
    b.insert(0, "a", now=0)
    b.insert(1, "b", now=10)
    b.undo()
    b.insert(1, "c", now=20)
    assert b.text == "ac"
    b.undo()
    assert b.text == "a"
    b.undo()
    assert b.text == ""
