import pytest
from undoredo import TextBuffer


def test_an_empty_delete_adds_no_step():
    b = TextBuffer("abc")
    b.delete(1, 1, now=0)
    b.delete(0, 0, now=1)
    b.delete(3, 3, now=2)
    assert b.text == "abc"
    assert b.can_undo is False
    assert b.undo() is False


def test_an_empty_delete_keeps_the_redo_history():
    b = TextBuffer("abc")
    b.insert(3, "d", now=0)
    b.undo()
    b.delete(2, 2, now=10)
    assert b.can_redo is True
    assert b.redo() is True
    assert b.text == "abcd"


def test_an_empty_delete_does_not_close_the_open_step():
    b = TextBuffer()
    b.insert(0, "a", now=0.0)
    b.delete(0, 0, now=0.2)
    b.insert(1, "b", now=0.4)
    assert b.text == "ab"
    b.undo()
    assert b.text == ""


def test_a_real_delete_in_the_same_place_does_close_it():
    b = TextBuffer()
    b.insert(0, "a", now=0.0)
    b.delete(0, 1, now=0.2)
    b.insert(0, "b", now=0.4)
    b.undo()
    assert b.text == ""
    b.undo()
    assert b.text == "a"


def test_an_empty_delete_still_checks_its_range():
    b = TextBuffer("abc")
    with pytest.raises(IndexError):
        b.delete(5, 5)
    with pytest.raises(IndexError):
        b.delete(-1, -1)
