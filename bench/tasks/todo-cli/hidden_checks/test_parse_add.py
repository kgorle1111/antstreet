import dataclasses

import pytest
from core import TodoList
from parse import Command, ParseError, parse_command


def test_plain_text():
    assert parse_command("add buy milk") == Command("add", text="buy milk")


def test_text_words_are_joined_with_single_spaces():
    assert parse_command("  add   buy \t  milk  ").text == "buy milk"


def test_priority_and_tags_anywhere():
    command = parse_command("add #home buy !1 milk #Errand")
    assert command == Command("add", text="buy milk", priority=1, tags=("home", "Errand"))


def test_defaults():
    command = parse_command("add x")
    assert command.priority is None
    assert command.tags == ()
    assert command.item_id is None
    assert command.status is None
    assert isinstance(command.tags, tuple)


def test_each_priority():
    assert [parse_command(f"add x !{n}").priority for n in (1, 2, 3)] == [1, 2, 3]
    assert parse_command("add x !01").priority == 1


@pytest.mark.parametrize("word", ["!0", "!4", "!10", "!99", "!00"])
def test_priority_out_of_range_is_an_error(word):
    with pytest.raises(ParseError):
        parse_command(f"add x {word}")


def test_priority_twice_is_an_error_even_when_equal():
    with pytest.raises(ParseError):
        parse_command("add x !1 !2")
    with pytest.raises(ParseError):
        parse_command("add x !1 !1")


@pytest.mark.parametrize("line", ["add", "add   ", "add #tag", "add !2", "add #a #b !1"])
def test_no_text_is_an_error(line):
    with pytest.raises(ParseError):
        parse_command(line)


def test_lone_markers_and_odd_words_are_text():
    command = parse_command("add # ! !x !1a a#b c!")
    assert command.text == "# ! !x !1a a#b c!"
    assert command.priority is None
    assert command.tags == ()


def test_hash_digit_is_a_tag():
    command = parse_command("add x #1")
    assert command.tags == ("1",)
    assert command.text == "x"


def test_repeated_tags_are_kept_as_written():
    assert parse_command("add x #a #A #a").tags == ("a", "A", "a")


def test_command_is_frozen():
    command = parse_command("add x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        command.text = "y"


def test_parsed_add_is_accepted_by_core():
    command = parse_command("add Pay rent !1 #Bills #bills")
    todos = TodoList()
    item_id = todos.add(command.text, command.priority or 2, command.tags)
    item = todos.get(item_id)
    assert (item.text, item.priority, item.tags) == ("Pay rent", 1, ("bills",))
