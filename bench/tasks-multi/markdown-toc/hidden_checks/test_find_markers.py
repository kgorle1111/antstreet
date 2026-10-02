import pytest
from inject import find_markers, update_toc

START = "<!-- toc -->"
END = "<!-- /toc -->"


def test_zero_based_line_indexes():
    assert find_markers(f"# T\n{START}\nold\n{END}\ntext\n") == (1, 3)
    assert find_markers(f"{START}\n{END}") == (0, 1)


def test_markers_with_surrounding_whitespace_count():
    assert find_markers(f"  {START}  \nx\n\t{END}\t\n") == (0, 2)


def test_markers_are_whole_lines():
    for text in (
        f"text {START}\n{END}",
        f"{START}\n{END} text",
        f"<!--toc-->\n{END}",
        f"{START.upper()}\n{END}",
    ):
        with pytest.raises(ValueError):
            find_markers(text)


@pytest.mark.parametrize(
    "text",
    [
        "# no markers\n",
        "",
        f"{START}\nonly start\n",
        f"only end\n{END}\n",
        f"{END}\n{START}\n",
        f"{START}\n{START}\n{END}\n",
        f"{START}\n{END}\n{END}\n",
        f"{START}\n{END}\n{START}\n{END}\n",
    ],
)
def test_wrong_marker_layouts(text):
    with pytest.raises(ValueError):
        find_markers(text)
    with pytest.raises(ValueError):
        update_toc(text)


def test_markers_inside_code_fences_are_ignored():
    text = f"```\n{START}\n{END}\n```\n{START}\ntoc\n{END}\n"
    assert find_markers(text) == (4, 6)


def test_markers_only_in_a_code_fence_are_missing():
    with pytest.raises(ValueError):
        find_markers(f"```\n{START}\n{END}\n```\n")


def test_a_fence_example_does_not_count_as_a_second_marker():
    text = f"{START}\n{END}\n\n~~~\n{START}\n{END}\n~~~\n"
    assert find_markers(text) == (0, 1)


def test_non_string_input():
    for bad in (None, 5, b"<!-- toc -->", ["x"]):
        with pytest.raises(ValueError):
            find_markers(bad)
        with pytest.raises(ValueError):
            update_toc(bad)
