import pytest
from core import TodoList
from parse import parse_command


def build():
    todos = TodoList()
    todos.add("c-low", 3, ["x"])
    todos.add("a-high", 1, ["y"])
    todos.add("b-mid", 2, ["x", "y"])
    todos.add("d-high", 1)
    todos.add("e-mid", 2)
    todos.done(5)
    return todos


def texts(items):
    return [i.text for i in items]


def test_default_is_open_items_ordered_by_priority_then_id():
    assert texts(build().items()) == ["a-high", "d-high", "b-mid", "c-low"]


def test_status_filters():
    todos = build()
    assert texts(todos.items("open")) == ["a-high", "d-high", "b-mid", "c-low"]
    assert texts(todos.items("done")) == ["e-mid"]
    assert texts(todos.items("all")) == ["a-high", "d-high", "b-mid", "e-mid", "c-low"]
    assert texts(todos.items(status="done")) == ["e-mid"]


def test_tag_filter_composes_with_status():
    todos = build()
    assert texts(todos.items(tag="x")) == ["b-mid", "c-low"]
    assert texts(todos.items("all", "y")) == ["a-high", "b-mid"]
    assert texts(todos.items("done", "x")) == []
    assert texts(todos.items(tag="nope")) == []


def test_tag_filter_is_case_and_space_insensitive():
    todos = build()
    assert texts(todos.items(tag=" X ")) == ["b-mid", "c-low"]
    assert texts(todos.items(tag="Y")) == ["a-high", "b-mid"]


def test_invalid_status_and_tag():
    todos = build()
    for bad in ("", "OPEN", "pending", None, 1):
        with pytest.raises(ValueError):
            todos.items(bad)
    with pytest.raises(ValueError):
        todos.items(tag="bad tag")


def test_returns_a_new_list_each_time():
    todos = build()
    first = todos.items()
    first.clear()
    assert len(todos.items()) == 4


def test_done_items_keep_their_priority_order():
    todos = TodoList()
    todos.add("p3", 3)
    todos.add("p1", 1)
    todos.add("p2", 2)
    for i in (1, 2, 3):
        todos.done(i)
    assert texts(todos.items("done")) == ["p1", "p2", "p3"]
    assert todos.items() == []


def test_parsed_list_command_matches_items_arguments():
    todos = build()
    command = parse_command("list all #x")
    tag = command.tags[0] if command.tags else None
    assert texts(todos.items(command.status, tag)) == ["b-mid", "c-low"]
