import pytest
from mdheadings import extract_headings


def levels_and_titles(text):
    return [(level, title) for level, title, _ in extract_headings(text)]


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_each_level_from_one_to_six(level):
    assert levels_and_titles("#" * level + " Title") == [(level, "Title")]


def test_headings_come_in_document_order():
    text = "# One\n\ntext\n\n## Two\n\n### Three\n\n## Four\n"
    assert levels_and_titles(text) == [(1, "One"), (2, "Two"), (3, "Three"), (2, "Four")]


@pytest.mark.parametrize(
    "line",
    [
        "#A",
        "##A",
        "####### Seven",
        "######## Eight",
        " # Indented",
        "  ## Indented",
        "\t# Tab indented",
        "Title\n=====",
        "Title\n-----",
        "text # not a heading",
        "#!shebang",
        "#hashtag",
    ],
)
def test_lines_that_are_not_headings(line):
    assert extract_headings(line) == []


def test_a_tab_after_the_hashes_is_enough():
    assert levels_and_titles("#\tTabbed") == [(1, "Tabbed")]
    assert levels_and_titles("##\t\tTwo tabs") == [(2, "Two tabs")]


def test_title_whitespace_is_trimmed_inner_whitespace_is_kept():
    assert levels_and_titles("#    Spaced   out title   ") == [(1, "Spaced   out title")]


def test_carriage_returns_at_line_ends_are_ignored():
    assert extract_headings("# A\r\n\r\n## B\r\n") == [(1, "A", "a"), (2, "B", "b")]


def test_inline_markup_stays_in_the_title():
    assert levels_and_titles("## The `code` *part* [link](u)") == [
        (2, "The `code` *part* [link](u)")
    ]


def test_no_headings_gives_an_empty_list():
    assert extract_headings("") == []
    assert extract_headings("plain\n\ntext only\n") == []


def test_a_heading_right_after_text_without_a_blank_line_still_counts():
    assert levels_and_titles("some text\n# Heading\nmore text") == [(1, "Heading")]


def test_the_result_is_a_list_of_three_tuples():
    result = extract_headings("# A")
    assert type(result) is list and type(result[0]) is tuple and len(result[0]) == 3
    assert type(result[0][0]) is int
