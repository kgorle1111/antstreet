import pytest
from headings import extract_headings, fenced_lines


def test_no_fences():
    assert fenced_lines("a\nb\n# c\n") == set()
    assert fenced_lines("") == set()


def test_simple_backtick_fence_includes_both_fence_lines():
    assert fenced_lines("a\n```\nb\n```\nc") == {2, 3, 4}


def test_tilde_fence_and_info_string():
    assert fenced_lines("~~~python\nx\n~~~\ny") == {1, 2, 3}
    assert fenced_lines("```python title\nx\n```") == {1, 2, 3}


def test_other_kind_of_fence_inside_does_not_close():
    text = "a\n```\nb\n~~~\nc\n```\nd\n~~~~\ne\n~~~\nf\n~~~~~\ng"
    assert fenced_lines(text) == {2, 3, 4, 5, 6, 8, 9, 10, 11, 12}


def test_closing_fence_must_be_at_least_as_long_and_bare():
    assert fenced_lines("````\nx\n```\ny\n````\nz") == {1, 2, 3, 4, 5}
    assert fenced_lines("```\nx\n``` not bare\ny\n```  \nz") == {1, 2, 3, 4, 5}


def test_unclosed_fence_runs_to_the_end():
    assert fenced_lines("a\n```\nb\nc") == {2, 3, 4}
    assert fenced_lines("```") == {1}


def test_indentation_limit_of_three_spaces():
    assert fenced_lines("   ```\nx\n   ```\ny") == {1, 2, 3}
    assert fenced_lines("    ```\nx\n    ```") == set()
    assert fenced_lines("```\nx\n    ```\ny\n```") == {1, 2, 3, 4, 5}


def test_two_backticks_are_not_a_fence():
    assert fenced_lines("``\nx\n``") == set()


def test_several_blocks_and_adjacent_blocks():
    text = "```\na\n```\n```\nb\n```\nc\n~~~\nd\n~~~\n"
    assert fenced_lines(text) == {1, 2, 3, 4, 5, 6, 8, 9, 10}


def test_returns_a_set_of_ints():
    result = fenced_lines("```\nx\n```")
    assert isinstance(result, set)
    assert all(isinstance(n, int) for n in result)


@pytest.mark.parametrize("bad", [None, 5, b"# x", ["# x"]])
def test_non_string_input(bad):
    with pytest.raises(ValueError):
        fenced_lines(bad)
    with pytest.raises(ValueError):
        extract_headings(bad)
