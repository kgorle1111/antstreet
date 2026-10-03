from core import TodoList
from shell import run_command


def test_the_example_session_from_the_idea():
    todos = TodoList()
    assert run_command(todos, "add buy milk !1 #home #Errand") == "Added #1: buy milk"
    assert run_command(todos, "list") == "[ ] #1 (p1) buy milk #home #errand"
    assert run_command(todos, "done 1") == "Done #1: buy milk"
    assert run_command(todos, "list") == "No items."
    assert run_command(todos, "list done") == "[x] #1 (p1) buy milk #home #errand"


def test_a_longer_session():
    todos = TodoList()
    assert run_command(todos, "add buy milk !1 #home #Errand") == "Added #1: buy milk"
    assert run_command(todos, "add call mum") == "Added #2: call mum"
    assert run_command(todos, "add   write   report  !3 #Work") == "Added #3: write report"
    assert run_command(todos, "list") == (
        "[ ] #1 (p1) buy milk #home #errand\n[ ] #2 (p2) call mum\n[ ] #3 (p3) write report #work"
    )
    assert run_command(todos, "done 2") == "Done #2: call mum"
    assert run_command(todos, "list") == (
        "[ ] #1 (p1) buy milk #home #errand\n[ ] #3 (p3) write report #work"
    )
    assert run_command(todos, "list all") == (
        "[ ] #1 (p1) buy milk #home #errand\n[x] #2 (p2) call mum\n[ ] #3 (p3) write report #work"
    )
    assert run_command(todos, "list #WORK") == "[ ] #3 (p3) write report #work"
    assert run_command(todos, "rm 1") == "Removed #1: buy milk"
    assert run_command(todos, "add new thing") == "Added #4: new thing"
    assert run_command(todos, "list done #home") == "No items."
    assert run_command(todos, "list all") == (
        "[x] #2 (p2) call mum\n[ ] #4 (p2) new thing\n[ ] #3 (p3) write report #work"
    )


def test_replies_have_no_trailing_newline():
    todos = TodoList()
    run_command(todos, "add a")
    for line in ["list", "list all", "done 1", "list done", "rm 1", "list"]:
        assert not run_command(todos, line).endswith("\n")


def test_done_twice_replies_the_same_and_stays_done():
    todos = TodoList()
    run_command(todos, "add a")
    assert run_command(todos, "done 1") == "Done #1: a"
    assert run_command(todos, "done 1") == "Done #1: a"
    assert todos.get(1).done is True


def test_text_is_replied_as_stored():
    todos = TodoList()
    assert run_command(todos, "add \t  spaced \t out   words  ") == "Added #1: spaced out words"
    assert run_command(todos, "done 1") == "Done #1: spaced out words"


def test_removed_text_is_replied_even_for_done_items():
    todos = TodoList()
    run_command(todos, "add temp !2")
    run_command(todos, "done 1")
    assert run_command(todos, "rm 1") == "Removed #1: temp"
    assert run_command(todos, "list all") == "No items."


def test_two_lists_do_not_share_state():
    one, two = TodoList(), TodoList()
    run_command(one, "add a")
    assert run_command(two, "list all") == "No items."
    assert run_command(two, "add b") == "Added #1: b"
    assert len(one) == 1 and len(two) == 1


def test_priority_zero_digit_forms_and_default():
    todos = TodoList()
    run_command(todos, "add a !01")
    run_command(todos, "add b")
    assert run_command(todos, "list") == "[ ] #1 (p1) a\n[ ] #2 (p2) b"
