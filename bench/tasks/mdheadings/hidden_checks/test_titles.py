import pytest
from mdheadings import extract_headings


def titles(text):
    return [title for _, title, _ in extract_headings(text)]


@pytest.mark.parametrize(
    ("line", "title"),
    [
        ("## A ##", "A"),
        ("## A ## ", "A"),
        ("# A #", "A"),
        ("# A #####", "A"),
        ("### A ###", "A"),
        ("## A \t##", "A"),
        ("## Two words ##", "Two words"),
        ("## A  ##   ", "A"),
    ],
)
def test_a_closing_sequence_is_removed(line, title):
    assert titles(line) == [title]


@pytest.mark.parametrize(
    ("line", "title"),
    [
        ("## C#", "C#"),
        ("# F# and C#", "F# and C#"),
        ("# A # B", "A # B"),
        ("## A##", "A##"),
        ("# #1 priority", "#1 priority"),
        ("## issue #12", "issue #12"),
        ("# a#b", "a#b"),
        ("## A ## B ##", "A ## B"),
    ],
)
def test_a_hash_not_preceded_by_whitespace_or_not_at_the_end_is_kept(line, title):
    assert titles(line) == [title]


@pytest.mark.parametrize(
    "line", ["#", "##", "## ", "#   ", "# #", "## ##", "### ###", "#\t", "# ##  "]
)
def test_a_heading_with_an_empty_title_is_ignored(line):
    assert extract_headings(line) == []


def test_empty_headings_do_not_disturb_their_neighbours():
    assert titles("# A\n#\n## \n# B") == ["A", "B"]


def test_empty_headings_do_not_use_up_anchors():
    assert extract_headings("# Setup\n#\n# Setup") == [
        (1, "Setup", "setup"),
        (1, "Setup", "setup-1"),
    ]
