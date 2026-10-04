from undoredo import TextBuffer


def test_initial_text_and_empty_default():
    assert TextBuffer().text == ""
    assert TextBuffer("hello").text == "hello"


def test_insert_at_start_middle_and_end():
    b = TextBuffer("ace")
    b.insert(1, "b", now=0)
    assert b.text == "abce"
    b.insert(0, ">", now=10)
    assert b.text == ">abce"
    b.insert(5, "<", now=20)
    assert b.text == ">abce<"
    b.insert(4, "d", now=30)
    assert b.text == ">abcde<"


def test_insert_into_empty_buffer_and_multi_character_text():
    b = TextBuffer()
    b.insert(0, "hello")
    assert b.text == "hello"
    b.insert(5, " world", now=50)
    assert b.text == "hello world"


def test_delete_ranges():
    b = TextBuffer("hello world")
    b.delete(5, 11, now=0)
    assert b.text == "hello"
    b.delete(0, 1, now=10)
    assert b.text == "ello"
    b.delete(1, 3, now=20)
    assert b.text == "eo"
    b.delete(0, 2, now=30)
    assert b.text == ""


def test_edits_return_none_and_text_is_a_str():
    b = TextBuffer("ab")
    assert b.insert(1, "x") is None
    assert b.delete(0, 1, now=5) is None
    assert isinstance(b.text, str)


def test_new_buffer_has_no_history():
    b = TextBuffer("abc")
    assert b.can_undo is False
    assert b.can_redo is False
    assert b.undo() is False
    assert b.redo() is False
    assert b.text == "abc"
