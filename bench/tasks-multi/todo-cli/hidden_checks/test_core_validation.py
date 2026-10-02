import pytest
from core import TodoList
from shell import run_command


@pytest.mark.parametrize("text", ["", "   ", "\n", " \t ", None, 5, b"x", "a\nb", "a\n"])
def test_bad_text(text):
    todos = TodoList()
    with pytest.raises(ValueError):
        todos.add(text)
    assert len(todos) == 0


@pytest.mark.parametrize("priority", [0, 4, -1, 2.0, True, False, "1", None])
def test_bad_priority(priority):
    todos = TodoList()
    with pytest.raises(ValueError):
        todos.add("x", priority)
    assert len(todos) == 0


@pytest.mark.parametrize("priority", [1, 2, 3])
def test_good_priority(priority):
    todos = TodoList()
    assert todos.get(todos.add("x", priority)).priority == priority


@pytest.mark.parametrize("tag", ["", " ", "a b", "a#b", "#a", "a.b", "é", "a/b", None, 3])
def test_bad_tags(tag):
    todos = TodoList()
    with pytest.raises(ValueError):
        todos.add("x", tags=[tag])
    assert len(todos) == 0


def test_tag_characters_allowed():
    todos = TodoList()
    item = todos.get(todos.add("x", tags=["a-b_c", "0", "-", "_", "Z9"]))
    assert item.tags == ("a-b_c", "0", "-", "_", "z9")


def test_shell_turns_core_errors_into_replies():
    todos = TodoList()
    reply = run_command(todos, "add thing #bad.tag")
    assert reply.startswith("Error: ")
    assert len(todos) == 0
    assert run_command(todos, "add thing #good") == "Added #1: thing"
