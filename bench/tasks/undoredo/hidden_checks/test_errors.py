import pytest
from undoredo import TextBuffer


@pytest.mark.parametrize("pos", [-1, 4, 100])
def test_insert_position_outside_the_text_raises_index_error(pos):
    b = TextBuffer("abc")
    with pytest.raises(IndexError):
        b.insert(pos, "x")
    assert b.text == "abc"
    assert b.can_undo is False


def test_insert_at_both_ends_is_valid():
    b = TextBuffer("abc")
    b.insert(0, "<", now=0)
    b.insert(4, ">", now=10)
    assert b.text == "<abc>"


@pytest.mark.parametrize("text", ["", None, 5])
def test_insert_needs_non_empty_text(text):
    b = TextBuffer("abc")
    with pytest.raises(ValueError):
        b.insert(1, text)
    assert b.text == "abc"
    assert b.can_undo is False


@pytest.mark.parametrize("start,end", [(-1, 2), (0, 4), (2, 1), (4, 4), (3, 9), (-2, -1)])
def test_bad_delete_range_raises_index_error(start, end):
    b = TextBuffer("abc")
    with pytest.raises(IndexError):
        b.delete(start, end)
    assert b.text == "abc"
    assert b.can_undo is False


def test_valid_extreme_delete_ranges():
    b = TextBuffer("abc")
    b.delete(0, 3)
    assert b.text == ""
    b.delete(0, 0, now=10)
    assert b.text == ""


def test_a_refused_edit_keeps_the_redo_history():
    b = TextBuffer("abc")
    b.insert(3, "d")
    b.undo()
    with pytest.raises(IndexError):
        b.insert(99, "x")
    with pytest.raises(ValueError):
        b.insert(0, "")
    assert b.can_redo is True
    assert b.redo() is True
    assert b.text == "abcd"


@pytest.mark.parametrize("window", [-1, -0.001])
def test_negative_merge_window_raises(window):
    with pytest.raises(ValueError):
        TextBuffer(merge_window=window)


@pytest.mark.parametrize("steps", [0, -1, 2.5])
def test_bad_max_steps_raises(steps):
    with pytest.raises(ValueError):
        TextBuffer(max_steps=steps)


def test_zero_window_and_one_step_are_valid():
    TextBuffer(merge_window=0, max_steps=1)
