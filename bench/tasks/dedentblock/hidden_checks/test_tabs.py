import pytest
from dedentblock import dedent


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\tx\n\ty", "x\ny"),
        ("\t\tx\n\ty", "\tx\ny"),
        ("\tx\n    y", "\tx\n    y"),
        ("    x\n\ty", "    x\n\ty"),
        ("\t  x\n\t\ty", "  x\n\ty"),
        ("  \tx\n  \t\ty", "x\n\ty"),
        ("  \tx\n\t  y", "  \tx\n\t  y"),
    ],
)
def test_tabs_and_spaces_are_compared_character_by_character(text, expected):
    assert dedent(text) == expected


def test_a_tab_is_not_eight_spaces():
    text = "\ta\n        b"
    assert dedent(text) == text


def test_mixed_indentation_is_only_cut_where_it_agrees():
    text = " \tdef f():\n \t\treturn 1\n \tx"
    assert dedent(text) == "def f():\n\treturn 1\nx"


def test_tabs_inside_the_text_are_untouched():
    assert dedent("  a\tb\n  c\t\td") == "a\tb\nc\t\td"


def test_the_removed_part_is_the_margin_prefix():
    # Both indentations are 3 characters long, but only the first character is shared.
    assert dedent("\t  a\n  \tb") == "\t  a\n  \tb"
    assert dedent(" \t a\n \t\tb") == " a\n\tb"
