from undoredo import TextBuffer


def separate_inserts(b, n):
    for i in range(n):
        b.insert(0, str(i), now=100.0 * i)


def test_only_max_steps_steps_can_be_undone():
    b = TextBuffer(max_steps=3)
    separate_inserts(b, 5)
    assert b.text == "43210"
    assert [b.undo() for _ in range(4)] == [True, True, True, False]
    assert b.text == "10"


def test_the_oldest_step_is_the_one_dropped():
    b = TextBuffer("start", max_steps=2)
    b.insert(5, "!", now=0)
    b.delete(0, 1, now=100)
    b.insert(0, "S", now=200)
    assert b.text == "Start!"
    assert b.undo() is True
    assert b.text == "tart!"
    assert b.undo() is True
    assert b.text == "start!"
    assert b.undo() is False
    assert b.text == "start!"


def test_a_single_step_buffer():
    b = TextBuffer("ab", max_steps=1)
    b.insert(2, "c", now=0)
    b.insert(3, "d", now=100)
    assert b.undo() is True
    assert b.text == "abc"
    assert b.undo() is False


def test_merged_inserts_do_not_count_against_the_limit():
    b = TextBuffer(max_steps=2)
    for i, ch in enumerate("abcdefgh"):
        b.insert(i, ch, now=0.1 * i)
    b.insert(0, "X", now=50)
    assert b.undo() is True
    assert b.text == "abcdefgh"
    assert b.undo() is True
    assert b.text == ""


def test_redo_still_works_after_steps_were_dropped():
    b = TextBuffer(max_steps=2)
    separate_inserts(b, 4)
    b.undo()
    b.undo()
    assert b.redo() is True
    assert b.redo() is True
    assert b.redo() is False
    assert b.text == "3210"


def test_the_default_keeps_a_hundred_steps():
    b = TextBuffer()
    separate_inserts(b, 130)
    undone = 0
    while b.undo():
        undone += 1
    assert undone == 100
