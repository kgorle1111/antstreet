import pytest
from mdheadings import extract_headings


def anchor(title):
    [(_, _, value)] = extract_headings("# " + title)
    return value


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Hello", "hello"),
        ("Hello World", "hello-world"),
        ("Hello, World!", "hello-world"),
        ("The `code` part", "the-code-part"),
        ("API v2.0 (beta)", "api-v20-beta"),
        ("Q&A: what's new?", "qa-whats-new"),
        ("snake_case and kebab-case", "snake_case-and-kebab-case"),
        ("ALL CAPS", "all-caps"),
        ("Section 1.2.3", "section-123"),
        ("100% sure", "100-sure"),
        ("a/b\\c", "abc"),
        ("*bold* and _italic_", "bold-and-_italic_"),
        ("[link](http://x.y)", "linkhttpxy"),
    ],
)
def test_anchor_from_title(title, expected):
    assert anchor(title) == expected


def test_spaces_are_not_merged():
    assert anchor("A  B") == "a--b"
    assert anchor("A - B") == "a---b"


def test_the_anchor_is_built_from_the_title_without_its_closing_hashes():
    assert extract_headings("## Hello World ##") == [(2, "Hello World", "hello-world")]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Café au lait", "café-au-lait"),
        ("Über uns", "über-uns"),
        ("日本語 text", "日本語-text"),
        ("Привет Мир", "привет-мир"),
        ("naïve – ideas", "naïve--ideas"),
    ],
)
def test_letters_beyond_ascii_are_kept_and_lowercased(title, expected):
    assert anchor(title) == expected


@pytest.mark.parametrize("title", ["!!!", "???", "...", "()", "``!"])
def test_a_title_with_nothing_left_gets_the_anchor_section(title):
    assert anchor(title) == "section"


def test_the_title_keeps_its_original_form():
    assert extract_headings("# Hello, World!") == [(1, "Hello, World!", "hello-world")]


def test_a_tab_inside_a_title_is_removed_from_the_anchor_not_turned_into_a_hyphen():
    assert anchor("A\tB") == "ab"
