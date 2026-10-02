import dataclasses

import pytest
from core import Item, TodoList
from shell import run_command


def test_ids_count_up_from_one():
    todos = TodoList()
    assert [todos.add("a"), todos.add("b"), todos.add("c")] == [1, 2, 3]
    assert len(todos) == 3


def test_item_fields_and_defaults():
    todos = TodoList()
    item_id = todos.add("  buy milk  ")
    item = todos.get(item_id)
    assert item == Item(1, "buy milk", 2, (), False)
    assert isinstance(item.tags, tuple)


def test_priority_and_tags_are_stored():
    todos = TodoList()
    item_id = todos.add("x", 1, ["Home", "errand"])
    assert todos.get(item_id) == Item(1, "x", 1, ("home", "errand"), False)


def test_tags_are_stripped_lowercased_and_deduplicated_in_order():
    todos = TodoList()
    item_id = todos.add("x", tags=[" B ", "a", "b", "A", "c_d-1", "a"])
    assert todos.get(item_id).tags == ("b", "a", "c_d-1")


def test_tags_may_be_any_iterable():
    todos = TodoList()
    assert todos.get(todos.add("x", tags=("t",))).tags == ("t",)
    assert todos.get(todos.add("y", tags=iter(["u", "v"]))).tags == ("u", "v")
    assert todos.get(todos.add("z", tags=[])).tags == ()


def test_item_is_frozen():
    item = Item(1, "a", 2, (), False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.done = True


def test_get_unknown_id():
    todos = TodoList()
    todos.add("a")
    for bad in (0, 2, -1, 99):
        with pytest.raises(KeyError):
            todos.get(bad)


def test_failed_add_uses_no_id_and_adds_nothing():
    todos = TodoList()
    todos.add("a")
    with pytest.raises(ValueError):
        todos.add("b", tags=["ok", "not ok"])
    with pytest.raises(ValueError):
        todos.add("", 1)
    assert len(todos) == 1
    assert todos.add("c") == 2


def test_the_shell_sees_what_core_stored():
    todos = TodoList()
    run_command(todos, "add Water plants !3 #Garden")
    assert todos.get(1) == Item(1, "Water plants", 3, ("garden",), False)
