import pytest
from inject import update_toc

BEFORE = """# Title

<!-- toc -->

<!-- /toc -->

## Intro
### Details
## Usage
"""

AFTER = """# Title

<!-- toc -->

- [Title](#title)
  - [Intro](#intro)
    - [Details](#details)
  - [Usage](#usage)

<!-- /toc -->

## Intro
### Details
## Usage
"""


def test_example_from_the_idea_exactly():
    assert update_toc(BEFORE) == AFTER


def test_idempotent():
    once = update_toc(BEFORE)
    assert update_toc(once) == once
    assert update_toc(update_toc(once)) == once


def test_stale_content_between_the_markers_is_replaced():
    stale = BEFORE.replace(
        "<!-- toc -->\n\n<!-- /toc -->",
        "<!-- toc -->\nold line\n# Stale heading\n- [gone](#gone)\n\n\n<!-- /toc -->",
    )
    assert update_toc(stale) == AFTER


def test_headings_in_the_old_region_never_count():
    text = "<!-- toc -->\n# Fake\n## Fake two\n<!-- /toc -->\n# Real\n"
    assert update_toc(text) == ("<!-- toc -->\n\n- [Real](#real)\n\n<!-- /toc -->\n# Real\n")


def test_everything_outside_the_markers_is_untouched():
    text = (
        "Intro text\n\n  <!-- toc -->  \nold\n\t<!-- /toc -->\t\n\n"
        "## B\ntrailing spaces   \n\n\n## A\nlast line without newline"
    )
    result = update_toc(text)
    assert result.startswith("Intro text\n\n  <!-- toc -->  \n\n- [B](#b)\n- [A](#a)\n\n")
    assert result.endswith(
        "\t<!-- /toc -->\t\n\n## B\ntrailing spaces   \n\n\n## A\nlast line without newline"
    )
    assert not result.endswith("\n")


def test_trailing_newline_is_preserved_either_way():
    with_nl = "<!-- toc -->\n<!-- /toc -->\n# A\n"
    without = "<!-- toc -->\n<!-- /toc -->\n# A"
    assert update_toc(with_nl).endswith("# A\n")
    assert update_toc(without).endswith("# A")
    assert update_toc(with_nl) == update_toc(without) + "\n"


def test_no_headings_leaves_a_single_empty_line():
    text = "intro\n<!-- toc -->\nold stuff\n<!-- /toc -->\nmore text\n"
    assert update_toc(text) == "intro\n<!-- toc -->\n\n<!-- /toc -->\nmore text\n"


def test_adjacent_markers():
    assert update_toc("<!-- toc -->\n<!-- /toc -->\n# A\n") == (
        "<!-- toc -->\n\n- [A](#a)\n\n<!-- /toc -->\n# A\n"
    )


def test_headings_before_and_after_the_markers_are_both_listed_in_order():
    text = "# Top\n<!-- toc -->\n<!-- /toc -->\n## Later\n# Last\n"
    assert update_toc(text) == (
        "# Top\n<!-- toc -->\n\n- [Top](#top)\n  - [Later](#later)\n- [Last](#last)\n\n"
        "<!-- /toc -->\n## Later\n# Last\n"
    )


def test_level_limits_are_passed_through():
    text = "<!-- toc -->\n<!-- /toc -->\n# A\n## B\n### C\n#### D\n"
    result = update_toc(text, min_level=2, max_level=3)
    assert "- [B](#b)\n  - [C](#c)\n" in result
    assert "[A]" not in result.split("<!-- /toc -->")[0]
    assert "[D]" not in result.split("<!-- /toc -->")[0]
    assert update_toc(text, 1, 1).split("<!-- /toc -->")[0] == "<!-- toc -->\n\n- [A](#a)\n\n"
    with pytest.raises(ValueError):
        update_toc(text, 3, 2)
    with pytest.raises(ValueError):
        update_toc(text, 0, 6)


def test_headings_inside_code_fences_are_not_listed():
    text = "<!-- toc -->\n<!-- /toc -->\n# A\n```\n# B\n```\n## C\n"
    result = update_toc(text)
    assert "[B]" not in result
    assert "- [A](#a)\n  - [C](#c)\n" in result


def test_duplicate_headings_get_distinct_links():
    text = "<!-- toc -->\n<!-- /toc -->\n## Usage\n## Usage\n"
    assert "- [Usage](#usage)\n- [Usage](#usage-1)\n" in update_toc(text)


def test_marker_lines_inside_a_fence_are_left_alone():
    text = "```\n<!-- toc -->\n```\n<!-- toc -->\n<!-- /toc -->\n# A\n"
    result = update_toc(text)
    assert result.startswith("```\n<!-- toc -->\n```\n<!-- toc -->\n\n- [A](#a)\n\n<!-- /toc -->")
