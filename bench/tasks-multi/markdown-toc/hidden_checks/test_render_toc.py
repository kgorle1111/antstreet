import pytest
from headings import Heading, extract_headings
from toc import render_toc


def H(level, text, anchor=None):
    return Heading(level, text, 1, anchor or text.lower().replace(" ", "-"))


def test_empty_list_renders_nothing():
    assert render_toc([]) == ""


def test_flat_list():
    assert render_toc([H(1, "One"), H(1, "Two")]) == "- [One](#one)\n- [Two](#two)\n"


def test_nesting_follows_the_stack_rule():
    headings = [H(1, "a"), H(2, "b"), H(3, "c"), H(2, "d"), H(1, "e")]
    assert render_toc(headings) == (
        "- [a](#a)\n  - [b](#b)\n    - [c](#c)\n  - [d](#d)\n- [e](#e)\n"
    )


def test_skipped_levels_indent_one_step_only():
    assert render_toc([H(1, "a"), H(3, "b"), H(2, "c")]) == (
        "- [a](#a)\n  - [b](#b)\n  - [c](#c)\n"
    )
    assert render_toc([H(1, "a"), H(4, "b"), H(6, "c")]) == (
        "- [a](#a)\n  - [b](#b)\n    - [c](#c)\n"
    )


def test_a_document_starting_deep_is_not_indented():
    assert render_toc([H(3, "a"), H(4, "b"), H(3, "c")]) == "- [a](#a)\n  - [b](#b)\n- [c](#c)\n"
    assert render_toc([H(2, "a"), H(1, "b")]) == "- [a](#a)\n- [b](#b)\n"


def test_going_back_up_past_several_levels():
    headings = [H(1, "a"), H(2, "b"), H(3, "c"), H(4, "d"), H(2, "e")]
    assert render_toc(headings).splitlines()[-1] == "  - [e](#e)"
    headings = [H(2, "a"), H(3, "b"), H(1, "c")]
    assert render_toc(headings) == "- [a](#a)\n  - [b](#b)\n- [c](#c)\n"


def test_level_filter_is_inclusive_and_does_not_change_the_nesting_of_the_rest():
    headings = [H(1, "a"), H(2, "b"), H(3, "c"), H(4, "d")]
    assert render_toc(headings, 2, 3) == "- [b](#b)\n  - [c](#c)\n"
    assert render_toc(headings, max_level=2) == "- [a](#a)\n  - [b](#b)\n"
    assert render_toc(headings, min_level=3) == "- [c](#c)\n  - [d](#d)\n"
    assert render_toc(headings, 3, 3) == "- [c](#c)\n"
    assert render_toc(headings, min_level=5) == ""


def test_filtered_out_headings_do_not_count_as_ancestors():
    headings = [H(1, "a"), H(3, "b"), H(2, "c"), H(3, "d")]
    assert render_toc(headings, 2, 3) == "- [b](#b)\n- [c](#c)\n  - [d](#d)\n"


def test_brackets_in_the_text_are_escaped():
    heading = Heading(1, "See [docs] and [x](y)", 1, "see-docs")
    assert render_toc([heading]) == "- [See \\[docs\\] and \\[x\\](y)](#see-docs)\n"


def test_text_is_used_as_written_and_anchor_as_given():
    heading = Heading(2, "Café `menu` *now*", 9, "custom-anchor")
    assert render_toc([heading]) == "- [Café `menu` *now*](#custom-anchor)\n"


@pytest.mark.parametrize(
    ("low", "high"),
    [
        (0, 6),
        (1, 7),
        (-1, 6),
        (3, 2),
        (1.0, 6),
        (1, 6.0),
        (True, 6),
        (1, True),
        ("1", 6),
        (None, 6),
    ],
)
def test_bad_levels(low, high):
    with pytest.raises(ValueError):
        render_toc([H(1, "a")], low, high)


def test_bad_levels_are_rejected_even_for_an_empty_list():
    with pytest.raises(ValueError):
        render_toc([], 4, 2)


def test_rendering_extracted_headings():
    text = "# Guide\n## Install\n### From source\n## Usage\n"
    assert render_toc(extract_headings(text)) == (
        "- [Guide](#guide)\n"
        "  - [Install](#install)\n"
        "    - [From source](#from-source)\n"
        "  - [Usage](#usage)\n"
    )
