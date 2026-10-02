import pytest
from wordwrap import wrap


def test_first_and_rest_indents_apply_to_their_lines():
    assert wrap("aa bb cc dd", 8, first_indent="> ", rest_indent="  ") == [
        "> aa bb",
        "  cc dd",
    ]


def test_indent_counts_toward_the_width():
    # "    aaa" is 7 long, so "bbb" cannot join it at width 10 (7 + 1 + 3 = 11).
    assert wrap("aaa bbb", 10, first_indent="    ") == ["    aaa", "bbb"]
    assert wrap("aaa bbb", 11, first_indent="    ") == ["    aaa bbb"]


def test_rest_indent_only_affects_later_lines():
    assert wrap("aa bb cc", 5, rest_indent="..") == ["aa bb", "..cc"]


def test_first_indent_only_affects_the_first_line():
    assert wrap("aa bb cc", 5, first_indent="* ") == ["* aa", "bb cc"]


def test_hanging_indent_for_a_list_item():
    lines = wrap("buy milk and eggs and bread", 12, first_indent="- ", rest_indent="  ")
    assert lines == ["- buy milk", "  and eggs", "  and bread"]


def test_each_line_is_measured_with_its_own_indent():
    lines = wrap("lorem ipsum dolor sit amet consectetur", 14, ">>> ", "> ")
    assert lines == [">>> lorem", "> ipsum dolor", "> sit amet", "> consectetur"]


@pytest.mark.parametrize("indent", ["\t", "  ", "    "])
def test_an_indent_is_any_string_and_each_character_counts_once(indent):
    lines = wrap("ab cd", len(indent) + 2, first_indent=indent, rest_indent=indent)
    assert lines == [indent + "ab", indent + "cd"]


def test_indent_is_not_added_to_text_without_words():
    assert wrap("", 10, first_indent="  ", rest_indent="  ") == []


def test_indents_default_to_empty():
    assert wrap("aa bb", 5) == wrap("aa bb", 5, "", "") == ["aa bb"]
