import pytest
from dedentblock import common_margin


@pytest.mark.parametrize(
    ("text", "margin"),
    [
        ("a", ""),
        ("  a", "  "),
        ("  a\n  b", "  "),
        ("    a\n  b", "  "),
        ("  a\n    b\n      c", "  "),
        ("a\n  b", ""),
        ("  a\nb", ""),
        ("\ta\n\tb", "\t"),
        ("\t\ta\n\tb", "\t"),
        ("  \ta\n  \tb", "  \t"),
        ("   a\n   b\n   c\n   d", "   "),
    ],
)
def test_margin_of_a_block(text, margin):
    assert common_margin(text) == margin


@pytest.mark.parametrize(
    ("text", "margin"),
    [
        ("\tx\n    y", ""),
        ("    x\n\ty", ""),
        ("\t  x\n\t\ty", "\t"),
        ("  \tx\n\t  y", ""),
        (" \tx\n \ty", " \t"),
        ("\t\tx\n\t\t y", "\t\t"),
    ],
)
def test_tab_and_space_are_different_characters(text, margin):
    assert common_margin(text) == margin


@pytest.mark.parametrize("text", ["", "\n", "\n\n", "   ", "  \n\t\n   ", " \t \t"])
def test_no_non_blank_line_gives_an_empty_margin(text):
    assert common_margin(text) == ""


def test_blank_lines_are_ignored():
    assert common_margin("  a\n\n  b") == "  "
    assert common_margin("    a\n \n    b") == "    "
    assert common_margin("    a\n\t\n    b\n") == "    "
    assert common_margin("\n\n    a\n\n") == "    "


def test_the_margin_is_a_prefix_not_a_count():
    assert common_margin("  \tx\n  y") == "  "
    assert common_margin("\t\tx\n\t y") == "\t"


def test_margin_is_a_str():
    assert type(common_margin("  a")) is str
    assert type(common_margin("")) is str
