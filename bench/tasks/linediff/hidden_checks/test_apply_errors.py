import pytest
from linediff import apply, diff


def test_kept_line_that_does_not_match():
    with pytest.raises(ValueError):
        apply(["a", "b"], [(" ", "a"), (" ", "X")])
    with pytest.raises(ValueError):
        apply(["a"], [(" ", "b")])


def test_removed_line_that_does_not_match():
    with pytest.raises(ValueError):
        apply(["a"], [("-", "b")])
    with pytest.raises(ValueError):
        apply(["a", "b"], [("-", "a"), ("-", "c")])


def test_lines_left_over():
    with pytest.raises(ValueError):
        apply(["a", "b"], [(" ", "a")])
    with pytest.raises(ValueError):
        apply(["a"], [])
    with pytest.raises(ValueError):
        apply(["a"], [("+", "x")])


def test_kept_or_removed_line_beyond_the_end_of_old():
    with pytest.raises(ValueError):
        apply([], [(" ", "a")])
    with pytest.raises(ValueError):
        apply([], [("-", "a")])
    with pytest.raises(ValueError):
        apply(["a"], [("-", "a"), ("-", "a")])


def test_additions_do_not_consume_old_lines():
    with pytest.raises(ValueError):
        apply(["a"], [("+", "a"), (" ", "b")])
    with pytest.raises(ValueError):
        apply(["a"], [("+", "a")])


def test_unknown_op():
    with pytest.raises(ValueError):
        apply(["a"], [("?", "a")])
    with pytest.raises(ValueError):
        apply(["a"], [(" ", "a"), ("x", "b")])
    with pytest.raises(ValueError):
        apply([], [("", "a")])


def test_diff_made_for_a_different_file():
    d = diff(["a", "b", "c"], ["a", "c"])
    assert apply(["a", "b", "c"], d) == ["a", "c"]
    with pytest.raises(ValueError):
        apply(["a", "b", "d"], d)
    with pytest.raises(ValueError):
        apply(["a", "b"], d)
    with pytest.raises(ValueError):
        apply(["a", "b", "c", "d"], d)
