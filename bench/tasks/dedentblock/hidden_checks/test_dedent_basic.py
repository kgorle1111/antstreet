import pytest
from dedentblock import dedent


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a", "a"),
        ("  a", "a"),
        ("  a\n  b", "a\nb"),
        ("    a\n  b", "  a\nb"),
        ("  a\n      b", "a\n    b"),
        ("a\n  b", "a\n  b"),
        ("  a\nb", "  a\nb"),
        ("    if x:\n        y\n    z", "if x:\n    y\nz"),
        ("\ta\n\t\tb", "a\n\tb"),
    ],
)
def test_the_margin_is_removed_from_every_line(text, expected):
    assert dedent(text) == expected


def test_a_longer_indentation_keeps_its_extra_part():
    assert dedent("  a\n      b") == "a\n    b"


def test_text_after_the_margin_is_kept_exactly():
    assert dedent("  a  b \n  c\t") == "a  b \nc\t"
    assert dedent("   x\n     y   ") == "x\n  y   "


def test_unindented_text_is_unchanged():
    text = "one\ntwo\n  three\n"
    assert dedent(text) == text


def test_the_empty_string():
    assert dedent("") == ""


def test_a_typical_triple_quoted_block():
    text = """
        def f():
            return 1

        print(f())
    """
    assert dedent(text) == "\ndef f():\n    return 1\n\nprint(f())\n"


def test_dedent_does_not_modify_a_dedented_block_again():
    once = dedent("    a\n      b\n    c")
    assert dedent(once) == once == "a\n  b\nc"
