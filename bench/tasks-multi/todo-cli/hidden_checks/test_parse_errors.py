import pytest
from core import TodoList
from parse import ParseError, parse_command
from shell import run_command


def test_parse_error_is_a_value_error():
    assert issubclass(ParseError, ValueError)
    with pytest.raises(ValueError):
        parse_command("")


@pytest.mark.parametrize("line", ["", " ", "\t\n", "   \n  "])
def test_blank_lines(line):
    with pytest.raises(ParseError):
        parse_command(line)


@pytest.mark.parametrize(
    "line", ["remove 1", "delete 1", "complete 1", "ls", "adds x", "#add", "1"]
)
def test_unknown_commands(line):
    with pytest.raises(ParseError):
        parse_command(line)


@pytest.mark.parametrize("line", [None, 5, b"add x", ["add", "x"]])
def test_non_string_lines(line):
    with pytest.raises(ParseError):
        parse_command(line)


def test_command_name_must_be_the_first_word():
    with pytest.raises(ParseError):
        parse_command("please add x")


def test_the_shell_reports_parse_errors_and_changes_nothing():
    todos = TodoList()
    todos.add("keep me")
    for line in ["", "frobnicate", "add", "add x !9", "done", "rm 1 2", "list #a #b"]:
        reply = run_command(todos, line)
        assert reply.startswith("Error: "), line
    assert len(todos) == 1
    assert todos.get(1).done is False
