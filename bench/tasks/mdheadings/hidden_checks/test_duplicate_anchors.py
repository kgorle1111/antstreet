from mdheadings import extract_headings


def anchors(text):
    return [anchor for _, _, anchor in extract_headings(text)]


def test_the_second_and_third_heading_with_the_same_anchor_get_a_counter():
    assert anchors("# Setup\n# Setup\n# Setup\n# Setup") == [
        "setup",
        "setup-1",
        "setup-2",
        "setup-3",
    ]


def test_counters_are_kept_separately_for_every_base_anchor():
    text = "# A\n# B\n# A\n# B\n# B\n# C\n# A"
    assert anchors(text) == ["a", "b", "a-1", "b-1", "b-2", "c", "a-2"]


def test_headings_of_different_levels_share_anchors():
    assert anchors("# Usage\n## Usage\n### Usage") == ["usage", "usage-1", "usage-2"]


def test_different_titles_with_the_same_anchor_count_as_duplicates():
    assert anchors("# Hello, World\n# hello world!\n# HELLO WORLD") == [
        "hello-world",
        "hello-world-1",
        "hello-world-2",
    ]


def test_the_titles_are_not_changed_by_the_counter():
    assert extract_headings("# Setup\n# Setup") == [(1, "Setup", "setup"), (1, "Setup", "setup-1")]


def test_the_fallback_anchor_is_counted_like_any_other():
    assert anchors("# !\n# ?\n# Ok\n# ...") == ["section", "section-1", "ok", "section-2"]


def test_headings_in_code_fences_do_not_use_up_anchors():
    text = "# Notes\n```\n# Notes\n```\n# Notes"
    assert anchors(text) == ["notes", "notes-1"]


def test_unique_headings_get_no_counter():
    assert anchors("# One\n# Two\n# Three") == ["one", "two", "three"]


def test_many_duplicates():
    text = "\n".join("## Item" for _ in range(12))
    assert anchors(text) == ["item"] + [f"item-{n}" for n in range(1, 12)]
