from linediff import diff


def check(old, new):
    ops = diff(old, new)
    assert [line for op, line in ops if op != "+"] == old
    assert [line for op, line in ops if op != "-"] == new
    return ops


def test_whitespace_and_case_matter():
    assert diff(["a"], ["a "]) == [("-", "a"), ("+", "a ")]
    assert diff([" a"], ["a"]) == [("-", " a"), ("+", "a")]
    assert diff(["A"], ["a"]) == [("-", "A"), ("+", "a")]


def test_trailing_newline_is_part_of_the_line():
    assert diff(["a\n"], ["a"]) == [("-", "a\n"), ("+", "a")]


def test_empty_string_is_a_line():
    assert diff([""], [""]) == [(" ", "")]
    assert diff([""], []) == [("-", "")]
    assert diff([], [""]) == [("+", "")]
    assert diff(["a", "", "b"], ["a", "b"]) == [(" ", "a"), ("-", ""), (" ", "b")]


def test_lines_that_look_like_ops():
    assert diff([" ", "-", "+"], [" ", "-", "+"]) == [(" ", " "), (" ", "-"), (" ", "+")]
    assert diff(["-x"], ["+x"]) == [("-", "-x"), ("+", "+x")]
    assert diff(["+ x", "- y"], ["+ x"]) == [(" ", "+ x"), ("-", "- y")]


def test_duplicate_lines():
    ops = check(["a", "a", "a"], ["a", "a"])
    assert sum(1 for op, _ in ops if op == " ") == 2
    ops = check(["a", "b", "a"], ["a"])
    assert sum(1 for op, _ in ops if op == " ") == 1
    ops = check(["a"], ["a", "a", "a"])
    assert sum(1 for op, _ in ops if op == "+") == 2


def test_long_lines_and_unicode():
    long = "x" * 10_000
    assert diff([long, "é"], [long, "e"]) == [(" ", long), ("-", "é"), ("+", "e")]
