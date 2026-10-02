import pytest
from headings import extract_headings, slugify


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Hello, World!", "hello-world"),
        ("a  b", "a--b"),
        ("C++ & Rust", "c--rust"),
        ("Snake_case-Name", "snake_case-name"),
        ("Café Crème", "café-crème"),
        ("UPPER lower", "upper-lower"),
        ("1. Getting started", "1-getting-started"),
        ("what's new?", "whats-new"),
        ("tab\there", "tabhere"),
        (" lead and trail ", "-lead-and-trail-"),
        ("a-b-c", "a-b-c"),
        ("--", "--"),
        ("日本語 テスト", "日本語-テスト"),
        ("`code` and **bold**", "code-and-bold"),
        ("[link](http://x.y)", "linkhttpxy"),
    ],
)
def test_slugify(text, slug):
    assert slugify(text) == slug


@pytest.mark.parametrize("text", ["!!!", "", "?!.,", "\t", "()"])
def test_nothing_left_gives_section(text):
    assert slugify(text) == "section"


def test_slugify_is_what_anchors_are_made_of():
    headings = extract_headings("# Hello, World!\n## Café menu\n### 3 + 4 = 7\n")
    assert [h.anchor for h in headings] == ["hello-world", "café-menu", "3--4--7"]
    assert [slugify(h.text) for h in headings] == [h.anchor for h in headings]


def test_a_heading_made_only_of_punctuation_gets_the_fallback_anchor():
    headings = extract_headings("# !!!\n# ???\n# Section\n")
    assert [h.anchor for h in headings] == ["section", "section-1", "section-2"]
