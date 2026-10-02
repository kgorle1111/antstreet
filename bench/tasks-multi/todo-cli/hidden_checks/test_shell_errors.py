import pytest
from core import TodoList
from shell import run_command


@pytest.mark.parametrize("command", ["done", "rm"])
def test_unknown_id_reply_is_exact_and_changes_nothing(command):
    todos = TodoList()
    todos.add("a")
    assert run_command(todos, f"{command} 7") == "Error: no item #7"
    assert len(todos) == 1 and todos.get(1).done is False


def test_removed_id_is_unknown():
    todos = TodoList()
    run_command(todos, "add a")
    run_command(todos, "rm 1")
    assert run_command(todos, "done 1") == "Error: no item #1"
    assert run_command(todos, "rm 1") == "Error: no item #1"


def test_leading_zeros_name_the_real_id_in_the_error():
    todos = TodoList()
    assert run_command(todos, "done 007") == "Error: no item #7"


def test_never_raises_for_user_mistakes():
    todos = TodoList()
    lines = [
        "",
        "   ",
        "nonsense",
        "add",
        "add !1",
        "add x !0",
        "add x !1 !1",
        "add x #bad.tag",
        "add x #ok #bad!",
        "done",
        "done x",
        "done 1 2",
        "rm 0",
        "rm -3",
        "rm 99",
        "list foo",
        "list done done",
        "list #a #b",
        "list #bad.tag",
        "list #",
    ]
    for line in lines:
        reply = run_command(todos, line)
        assert isinstance(reply, str)
        assert reply.startswith("Error: "), line
    assert len(todos) == 0


def test_a_failed_add_does_not_burn_an_id():
    todos = TodoList()
    assert run_command(todos, "add x #bad.tag").startswith("Error: ")
    assert run_command(todos, "add y") == "Added #1: y"


def test_errors_do_not_stop_later_commands():
    todos = TodoList()
    assert run_command(todos, "oops").startswith("Error: ")
    assert run_command(todos, "add fine") == "Added #1: fine"
    assert run_command(todos, "done 2") == "Error: no item #2"
    assert run_command(todos, "done 1") == "Done #1: fine"


def test_empty_list_replies():
    todos = TodoList()
    for line in ["list", "list done", "list all", "list #x", "list all #x"]:
        assert run_command(todos, line) == "No items."
