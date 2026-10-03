from headings import extract_headings
from toc import render_toc


def anchors(markdown):
    return [h.anchor for h in extract_headings(markdown)]


def test_unique_headings_keep_their_slug():
    assert anchors("# One\n## Two\n### Three\n") == ["one", "two", "three"]


def test_repeats_get_numbered_suffixes():
    assert anchors("# A\n# A\n# A\n# A\n") == ["a", "a-1", "a-2", "a-3"]


def test_a_taken_suffix_is_skipped():
    assert anchors("# A\n# A\n# A-1\n# A\n") == ["a", "a-1", "a-1-1", "a-2"]


def test_a_natural_suffix_heading_claims_its_anchor_first():
    assert anchors("# A\n# A-1\n# A\n") == ["a", "a-1", "a-2"]


def test_headings_differing_only_in_case_or_punctuation_collide():
    assert anchors("# Hello\n# hello\n# HELLO!\n") == ["hello", "hello-1", "hello-2"]


def test_different_levels_still_collide():
    assert anchors("# Notes\n## Notes\n### Notes\n") == ["notes", "notes-1", "notes-2"]


def test_headings_in_code_fences_do_not_use_up_anchors():
    assert anchors("# A\n```\n# A\n```\n# A\n") == ["a", "a-1"]


def test_skipped_empty_headings_do_not_use_up_anchors():
    assert anchors("##\n# Section\n## ##\n# Section\n") == ["section", "section-1"]


def test_the_toc_links_use_the_numbered_anchors():
    text = "# Usage\n## Examples\n# Usage\n## Examples\n"
    assert render_toc(extract_headings(text)) == (
        "- [Usage](#usage)\n"
        "  - [Examples](#examples)\n"
        "- [Usage](#usage-1)\n"
        "  - [Examples](#examples-1)\n"
    )


def test_anchors_are_unique_across_a_big_document():
    text = "".join(f"## Topic {n % 7}\n" for n in range(100))
    found = anchors(text)
    assert len(found) == len(set(found)) == 100
