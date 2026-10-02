import pytest
from core import TodoList
from shell import run_command


def test_done_marks_the_item():
    todos = TodoList()
    a, b = todos.add("a"), todos.add("b")
    todos.done(a)
    assert todos.get(a).done is True
    assert todos.get(b).done is False
    assert todos.get(a).text == "a"


def test_done_twice_is_fine():
    todos = TodoList()
    a = todos.add("a")
    todos.done(a)
    todos.done(a)
    assert todos.get(a).done is True
    assert len(todos) == 1


def test_done_unknown_id_is_a_key_error():
    todos = TodoList()
    with pytest.raises(KeyError):
        todos.done(1)
    a = todos.add("a")
    with pytest.raises(KeyError):
        todos.done(a + 1)


def test_remove_deletes_the_item():
    todos = TodoList()
    a, b = todos.add("a"), todos.add("b")
    assert todos.remove(a) is None
    assert len(todos) == 1
    with pytest.raises(KeyError):
        todos.get(a)
    assert [i.id for i in todos.items("all")] == [b]


def test_remove_unknown_or_twice_is_a_key_error():
    todos = TodoList()
    a = todos.add("a")
    todos.remove(a)
    with pytest.raises(KeyError):
        todos.remove(a)
    with pytest.raises(KeyError):
        todos.remove(42)


def test_ids_are_never_reused():
    todos = TodoList()
    a, b, c = todos.add("a"), todos.add("b"), todos.add("c")
    todos.remove(c)
    assert todos.add("d") == 4
    todos.remove(a)
    todos.remove(b)
    assert todos.add("e") == 5
    assert [i.id for i in todos.items("all")] == [4, 5]


def test_done_items_can_be_removed_and_len_counts_both():
    todos = TodoList()
    a = todos.add("a")
    todos.add("b")
    todos.done(a)
    assert len(todos) == 2
    todos.remove(a)
    assert len(todos) == 1


def test_shell_commands_drive_the_same_state():
    todos = TodoList()
    run_command(todos, "add one")
    run_command(todos, "add two")
    run_command(todos, "done 1")
    run_command(todos, "rm 2")
    assert todos.get(1).done is True
    assert len(todos) == 1
    run_command(todos, "add three")
    assert [i.id for i in todos.items("all")] == [1, 3]
