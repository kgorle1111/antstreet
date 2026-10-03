from dedentblock import common_margin, dedent


def test_a_carriage_return_is_content_not_a_line_end():
    assert dedent("  a\r\n  b\r\n") == "a\r\nb\r\n"
    assert common_margin("  a\r\n  b\r\n") == "  "


def test_a_line_of_spaces_and_a_carriage_return_is_not_blank():
    # "  \r" holds a character that is not a space or tab, so it counts for the margin.
    assert common_margin("    a\n  \r") == "  "
    assert dedent("    a\n  \r") == "  a\n\r"


def test_a_non_breaking_space_is_content():
    assert common_margin("   a\n  b") == "  "
    assert dedent("   a\n  b") == " a\nb"
    assert common_margin(" a\n  b") == ""
    assert dedent(" a\n  b") == " a\n  b"


def test_a_line_holding_only_a_non_breaking_space_is_not_blank():
    assert common_margin("    a\n ") == ""
    assert dedent("    a\n ") == "    a\n "


def test_a_form_feed_or_vertical_tab_is_content():
    assert common_margin("  \x0ca\n  b") == "  "
    assert common_margin("\x0ca\n  b") == ""
    assert common_margin("  a\n\x0b") == ""


def test_other_unicode_whitespace_is_not_indentation():
    assert common_margin(" a\n b") == ""
    assert dedent(" a\n b") == " a\n b"


def test_non_ascii_text_after_the_margin_is_kept():
    assert dedent("  café\n    €") == "café\n  €"
