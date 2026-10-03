from undoredo import TextBuffer


def type_text(b, word, start=0.0, gap=0.1):
    now = start
    for i, ch in enumerate(word):
        b.insert(i, ch, now=now)
        now += gap


def test_quick_typing_is_one_undo_step():
    b = TextBuffer()
    type_text(b, "hello", gap=0.2)
    assert b.text == "hello"
    assert b.undo() is True
    assert b.text == ""
    assert b.undo() is False


def test_a_merged_step_redoes_as_one():
    b = TextBuffer()
    type_text(b, "hello")
    b.undo()
    assert b.redo() is True
    assert b.text == "hello"
    assert b.redo() is False


def test_exactly_the_window_still_merges():
    b = TextBuffer(merge_window=1.0)
    b.insert(0, "a", now=10.0)
    b.insert(1, "b", now=11.0)
    b.undo()
    assert b.text == ""


def test_just_over_the_window_starts_a_new_step():
    b = TextBuffer(merge_window=1.0)
    b.insert(0, "a", now=10.0)
    b.insert(1, "b", now=11.5)
    b.undo()
    assert b.text == "a"
    b.undo()
    assert b.text == ""


def test_each_merged_insert_renews_the_window():
    b = TextBuffer(merge_window=1.0)
    for i, ch in enumerate("abcdef"):
        b.insert(i, ch, now=0.9 * i)
    assert b.text == "abcdef"
    b.undo()
    assert b.text == ""


def test_default_window_is_one_second():
    b = TextBuffer()
    b.insert(0, "a", now=0.0)
    b.insert(1, "b", now=1.0)
    b.insert(2, "c", now=2.5)
    b.undo()
    assert b.text == "ab"


def test_multi_character_inserts_merge_by_the_end_of_the_text_so_far():
    b = TextBuffer("..")
    b.insert(1, "ab", now=0.0)
    b.insert(3, "cd", now=0.5)
    assert b.text == ".abcd."
    b.undo()
    assert b.text == ".."


def test_a_larger_window():
    b = TextBuffer(merge_window=30)
    b.insert(0, "a", now=0)
    b.insert(1, "b", now=29)
    b.insert(2, "c", now=58)
    b.insert(3, "d", now=89)
    b.undo()
    assert b.text == "abc"
    b.undo()
    assert b.text == ""
