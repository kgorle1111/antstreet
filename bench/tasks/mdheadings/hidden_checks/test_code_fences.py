import pytest
from mdheadings import extract_headings


def titles(text):
    return [title for _, title, _ in extract_headings(text)]


def test_a_heading_inside_a_backtick_fence_is_ignored():
    assert titles("# Real\n```\n# comment\n## also a comment\n```\n# After") == ["Real", "After"]


def test_a_heading_inside_a_tilde_fence_is_ignored():
    assert titles("# Real\n~~~\n# comment\n~~~\n# After") == ["Real", "After"]


def test_the_opening_fence_may_have_an_info_string():
    text = "# A\n```python\n# not a heading\nprint(1)\n```\n# B"
    assert titles(text) == ["A", "B"]


def test_a_tilde_line_does_not_close_a_backtick_fence():
    assert titles("```\n~~~\n# inside\n~~~\n```\n# out") == ["out"]


def test_a_backtick_line_does_not_close_a_tilde_fence():
    assert titles("~~~\n```\n# inside\n```\n~~~\n# out") == ["out"]


def test_a_shorter_fence_does_not_close_a_longer_one():
    assert titles("````\n# inside\n```\n# still inside\n````\n# out") == ["out"]


def test_a_longer_fence_closes_a_shorter_one():
    assert titles("```\n# inside\n`````\n# out") == ["out"]
    assert titles("~~~\n# inside\n~~~~~~\n# out") == ["out"]


def test_a_fence_that_is_never_closed_runs_to_the_end():
    assert titles("# A\n```\n# B\n## C\n") == ["A"]


def test_headings_between_two_fences_count():
    text = "```\n# one\n```\n# between\n~~~\n# two\n~~~\n"
    assert titles(text) == ["between"]


def test_text_that_only_contains_backticks_inline_is_not_a_fence():
    assert titles("a ``` b\n# A\n`` x\n# B") == ["A", "B"]


def test_two_backticks_are_not_a_fence():
    assert titles("``\n# A\n``") == ["A"]


def test_an_indented_fence_marker_does_not_open_a_fence():
    assert titles("  ```\n# A\n") == ["A"]


def test_fence_lines_with_carriage_returns():
    assert titles("```\r\n# no\r\n```\r\n# yes\r\n") == ["yes"]


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~~"])
def test_headings_after_a_closed_fence_are_found_again(fence):
    text = f"{fence}\n# x\n{fence}\n# y\n{fence}\n# z\n{fence}\n# w"
    assert titles(text) == ["y", "w"]
