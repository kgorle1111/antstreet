from linediff import diff


def test_both_empty():
    assert diff([], []) == []


def test_identical_lists_are_all_kept():
    assert diff(["a", "b"], ["a", "b"]) == [(" ", "a"), (" ", "b")]


def test_everything_added_or_removed():
    assert diff([], ["a", "b"]) == [("+", "a"), ("+", "b")]
    assert diff(["a", "b"], []) == [("-", "a"), ("-", "b")]


def test_single_removal_and_insertion():
    assert diff(["a", "b", "c"], ["a", "c"]) == [(" ", "a"), ("-", "b"), (" ", "c")]
    assert diff(["a", "c"], ["a", "b", "c"]) == [(" ", "a"), ("+", "b"), (" ", "c")]


def test_replacement_is_removal_then_addition():
    assert diff(["a"], ["b"]) == [("-", "a"), ("+", "b")]
    assert diff(["x", "a", "y"], ["x", "b", "y"]) == [
        (" ", "x"),
        ("-", "a"),
        ("+", "b"),
        (" ", "y"),
    ]


def test_change_at_both_ends():
    assert diff(["a", "k", "b"], ["c", "k", "d"]) == [
        ("-", "a"),
        ("+", "c"),
        (" ", "k"),
        ("-", "b"),
        ("+", "d"),
    ]


def test_returns_list_of_tuples():
    result = diff(["a"], ["a", "b"])
    assert isinstance(result, list)
    assert all(isinstance(item, tuple) and len(item) == 2 for item in result)


def test_arguments_are_not_modified():
    old, new = ["a", "b", "c"], ["c", "b", "a", "d"]
    diff(old, new)
    assert old == ["a", "b", "c"]
    assert new == ["c", "b", "a", "d"]
