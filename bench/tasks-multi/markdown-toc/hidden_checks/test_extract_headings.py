from headings import Heading, extract_headings


def summary(markdown):
    return [(h.level, h.text, h.line) for h in extract_headings(markdown)]


def test_levels_one_to_six():
    text = "# a\n## b\n### c\n#### d\n##### e\n###### f\n"
    assert summary(text) == [
        (1, "a", 1),
        (2, "b", 2),
        (3, "c", 3),
        (4, "d", 4),
        (5, "e", 5),
        (6, "f", 6),
    ]


def test_heading_fields_and_type():
    [heading] = extract_headings("intro\n\n## Some Title\n")
    assert heading == Heading(2, "Some Title", 3, "some-title")
    assert isinstance(heading, Heading)


def test_not_headings():
    text = "#hashtag\n####### seven\n    # four spaces\n text # not at start\n#\n"
    assert summary(text) == []


def test_up_to_three_spaces_of_indentation():
    assert summary("   ### ok\n  ## ok2\n # ok3\n") == [(3, "ok", 1), (2, "ok2", 2), (1, "ok3", 3)]


def test_text_is_stripped_and_tabs_may_follow_the_hashes():
    assert summary("#   spaced   \n##\ttabbed\t\n") == [(1, "spaced", 1), (2, "tabbed", 2)]


def test_closing_sequence_is_removed():
    assert summary("## Title ##\n# Other #\n### x ###   \n#### y ####\t\n") == [
        (2, "Title", 1),
        (1, "Other", 2),
        (3, "x", 3),
        (4, "y", 4),
    ]
    assert summary("# a # #\n") == [(1, "a #", 1)]


def test_hashes_that_are_not_a_closing_sequence_stay():
    assert summary("## C#\n# F# and C#\n# #hashtag\n## a#b\n") == [
        (2, "C#", 1),
        (1, "F# and C#", 2),
        (1, "#hashtag", 3),
        (2, "a#b", 4),
    ]


def test_empty_headings_are_skipped_but_still_count_lines():
    text = "##\n## ##\n#\n###   \n# real\n"
    assert summary(text) == [(1, "real", 5)]


def test_inline_markup_is_kept_in_the_text():
    [heading] = extract_headings("## Using `code`, *emphasis* and [links](http://x)\n")
    assert heading.text == "Using `code`, *emphasis* and [links](http://x)"


def test_headings_in_fenced_blocks_are_ignored():
    text = "# one\n```\n# not\n## not either\n```\n## two\n~~~\n# nope\n~~~\n### three\n"
    assert summary(text) == [(1, "one", 1), (2, "two", 6), (3, "three", 10)]


def test_unclosed_fence_hides_the_rest():
    assert summary("# one\n```\n# hidden\n## hidden\n") == [(1, "one", 1)]


def test_setext_headings_are_not_recognised():
    assert summary("Title\n=====\nSub\n---\n") == []


def test_line_numbers_count_every_line_including_blank_and_fenced_ones():
    text = "\n\n# a\n\n```\ncode\n```\ntext\n## b"
    assert summary(text) == [(1, "a", 3), (2, "b", 9)]


def test_empty_and_heading_free_documents():
    assert extract_headings("") == []
    assert extract_headings("just text\nmore text\n") == []


def test_no_trailing_newline_is_fine():
    assert summary("# a\n## b") == [(1, "a", 1), (2, "b", 2)]
