from undoredo import TextBuffer


def test_an_insert_that_does_not_continue_the_text_starts_a_new_step():
    b = TextBuffer()
    b.insert(0, "ab", now=0.0)
    b.insert(0, "X", now=0.1)
    assert b.text == "Xab"
    b.undo()
    assert b.text == "ab"
    b.undo()
    assert b.text == ""


def test_insert_in_the_middle_of_the_previous_text_does_not_merge():
    b = TextBuffer()
    b.insert(0, "abc", now=0.0)
    b.insert(1, "X", now=0.1)
    b.undo()
    assert b.text == "abc"


def test_a_delete_never_merges_and_closes_the_step_before_it():
    b = TextBuffer()
    b.insert(0, "ab", now=0.0)
    b.delete(1, 2, now=0.1)
    b.insert(1, "c", now=0.2)
    assert b.text == "ac"
    b.undo()
    assert b.text == "a"
    b.undo()
    assert b.text == "ab"
    b.undo()
    assert b.text == ""


def test_consecutive_deletes_are_separate_steps():
    b = TextBuffer("abcd")
    b.delete(3, 4, now=0.0)
    b.delete(2, 3, now=0.1)
    b.undo()
    assert b.text == "abc"
    b.undo()
    assert b.text == "abcd"


def test_zero_window_merges_only_inserts_at_the_same_time():
    b = TextBuffer(merge_window=0)
    b.insert(0, "a", now=5.0)
    b.insert(1, "b", now=5.0)
    b.insert(2, "c", now=5.1)
    b.undo()
    assert b.text == "ab"
    b.undo()
    assert b.text == ""


def test_a_gap_in_the_typing_splits_it_into_two_steps():
    b = TextBuffer()
    b.insert(0, "a", now=0.0)
    b.insert(1, "b", now=0.5)
    b.insert(2, "c", now=5.0)
    b.insert(3, "d", now=5.5)
    assert b.text == "abcd"
    b.undo()
    assert b.text == "ab"
    b.undo()
    assert b.text == ""


def test_a_new_step_after_a_non_merge_can_itself_be_merged_into():
    b = TextBuffer()
    b.insert(0, "a", now=0.0)
    b.insert(0, "X", now=0.2)
    b.insert(1, "Y", now=0.4)
    assert b.text == "XYa"
    b.undo()
    assert b.text == "a"
