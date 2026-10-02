import pytest
from parse import Command, ParseError, parse_command


@pytest.mark.parametrize("name", ["done", "rm"])
def test_id_commands(name):
    assert parse_command(f"{name} 3") == Command(name, item_id=3)
    assert parse_command(f"  {name}   12  ") == Command(name, item_id=12)
    assert parse_command(f"{name} 007") == Command(name, item_id=7)
    assert parse_command(f"{name} 1").item_id == 1
    assert isinstance(parse_command(f"{name} 10").item_id, int)


@pytest.mark.parametrize("name", ["done", "rm"])
@pytest.mark.parametrize(
    "rest", ["", " 1 2", " 0", " -1", " +1", " x", " 1.5", " #1", " 1a", " ٣", " 00"]
)
def test_id_commands_reject_bad_arguments(name, rest):
    with pytest.raises(ParseError):
        parse_command(name + rest)


def test_list_defaults_to_open():
    assert parse_command("list") == Command("list", status="open")
    assert parse_command("list").tags == ()


def test_list_status_and_tag_in_either_order():
    assert parse_command("list done") == Command("list", status="done")
    assert parse_command("list all") == Command("list", status="all")
    assert parse_command("list #Home") == Command("list", status="open", tags=("Home",))
    assert parse_command("list done #home") == Command("list", status="done", tags=("home",))
    assert parse_command("list #home all") == Command("list", status="all", tags=("home",))


def test_names_and_status_words_are_case_insensitive():
    assert parse_command("LIST DONE") == Command("list", status="done")
    assert parse_command("List All #X") == Command("list", status="all", tags=("X",))
    assert parse_command("ADD Thing").name == "add"
    assert parse_command("Done 4") == Command("done", item_id=4)
    assert parse_command("RM 4").name == "rm"


@pytest.mark.parametrize(
    "line",
    ["list done all", "list open done", "list #a #b", "list #a #a", "list foo", "list #", "list 1"],
)
def test_list_errors(line):
    with pytest.raises(ParseError):
        parse_command(line)


def test_tabs_and_extra_spaces_separate_words():
    assert parse_command("\tlist\t\tdone   #x \n") == Command("list", status="done", tags=("x",))
