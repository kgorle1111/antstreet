import pytest
from dedentblock import dedent


def test_blank_lines_do_not_lower_the_margin():
    assert dedent("    a\n\n    b") == "a\n\nb"
    assert dedent("    a\n  \n    b") == "a\n\nb"


def test_a_whitespace_only_line_becomes_empty():
    assert dedent("  a\n   \n  b") == "a\n\nb"
    assert dedent("  a\n\t\t\n  b") == "a\n\nb"
    assert dedent("  a\n \t \n  b") == "a\n\nb"


def test_a_whitespace_only_line_shorter_than_the_margin_becomes_empty_too():
    assert dedent("      a\n \n      b") == "a\n\nb"


def test_a_whitespace_only_line_longer_than_the_margin_becomes_empty_not_trimmed():
    assert dedent("  a\n          \n  b") == "a\n\nb"


def test_leading_and_trailing_blank_lines_are_kept_as_empty_lines():
    assert dedent("\n\n  a\n  b\n\n") == "\n\na\nb\n\n"
    assert dedent("   \n  a\n   ") == "\na\n"


def test_a_trailing_newline_stays():
    assert dedent("  a\n  b\n") == "a\nb\n"
    assert dedent("  a\n  b").endswith("b") and not dedent("  a\n  b").endswith("\n")


def test_the_number_of_lines_never_changes():
    for text in ["", "\n", "\n\n\n", "  a\n\n  b\n", "x", "\n  x\n \n"]:
        assert dedent(text).count("\n") == text.count("\n")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        (" ", ""),
        ("  \n\t", "\n"),
        ("\n", "\n"),
        ("   \n   \n   ", "\n\n"),
        ("\t\t\n \t \n", "\n\n"),
    ],
)
def test_text_with_no_non_blank_line_becomes_only_empty_lines(text, expected):
    assert dedent(text) == expected
