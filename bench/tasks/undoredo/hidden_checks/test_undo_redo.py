from undoredo import TextBuffer


def test_undo_an_insert_and_redo_it():
    b = TextBuffer("abc")
    b.insert(3, "def", now=0)
    assert b.can_undo is True
    assert b.can_redo is False
    assert b.undo() is True
    assert b.text == "abc"
    assert b.can_undo is False
    assert b.can_redo is True
    assert b.redo() is True
    assert b.text == "abcdef"
    assert b.can_redo is False
    assert b.can_undo is True


def test_undo_a_delete_puts_the_text_back_where_it_was():
    b = TextBuffer("hello world")
    b.delete(2, 7, now=0)
    assert b.text == "heorld"
    assert b.undo() is True
    assert b.text == "hello world"
    assert b.redo() is True
    assert b.text == "heorld"


def test_several_steps_undo_in_reverse_order():
    b = TextBuffer("abc")
    b.insert(0, "X", now=0)
    b.delete(1, 3, now=10)
    b.insert(2, "YZ", now=20)
    assert b.text == "XcYZ"
    texts = []
    while b.undo():
        texts.append(b.text)
    assert texts == ["Xc", "Xabc", "abc"]
    redone = []
    while b.redo():
        redone.append(b.text)
    assert redone == ["Xabc", "Xc", "XcYZ"]


def test_undo_and_redo_with_nothing_left_return_false_and_change_nothing():
    b = TextBuffer("ab")
    b.insert(2, "c", now=0)
    assert b.undo() is True
    assert b.undo() is False
    assert b.text == "ab"
    assert b.redo() is True
    assert b.redo() is False
    assert b.text == "abc"


def test_undo_redo_round_trips_leave_the_text_unchanged():
    b = TextBuffer("0123456789")
    b.delete(0, 3, now=0)
    b.insert(4, "ab", now=10)
    b.delete(2, 6, now=20)
    final = b.text
    for _ in range(3):
        assert b.undo() is True
    assert b.text == "0123456789"
    for _ in range(3):
        assert b.redo() is True
    assert b.text == final


def test_partial_undo_then_redo_one_at_a_time():
    b = TextBuffer()
    b.insert(0, "a", now=0)
    b.insert(0, "b", now=10)
    b.insert(0, "c", now=20)
    assert b.text == "cba"
    b.undo()
    b.undo()
    assert b.text == "a"
    b.redo()
    assert b.text == "ba"
    assert b.can_redo is True
    assert b.can_undo is True
