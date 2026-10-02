import pytest
from reader import read_table


@pytest.mark.parametrize("text", ["", "\n", "\n\n\n", "﻿", "\r\n"])
def test_no_header_at_all(text):
    with pytest.raises(ValueError):
        read_table(text)


@pytest.mark.parametrize("text", [None, 5, b"a,b\n1,2\n", ["a,b"]])
def test_non_string_input(text):
    with pytest.raises(ValueError):
        read_table(text)


@pytest.mark.parametrize(
    "text",
    ["a,a\n1,2\n", "a,,c\n1,2,3\n", "a,b,\n1,2,3\n", " a , a\n1,2\n", "a, \n1,2\n"],
)
def test_bad_header_names(text):
    with pytest.raises(ValueError):
        read_table(text)


def test_names_that_differ_only_by_case_are_different():
    assert read_table("a,A\n1,2\n").columns == ("a", "A")


@pytest.mark.parametrize(
    "text",
    ["a,b\n1\n", "a,b\n1,2,3\n", "a,b\n1,2\n3\n", "a\n1,2\n", "a,b\n1,2\n\n3,4,5\n"],
)
def test_ragged_rows(text):
    with pytest.raises(ValueError):
        read_table(text)


def test_unterminated_quote():
    with pytest.raises(ValueError):
        read_table('a,b\n1,"oops\n')
    with pytest.raises(ValueError):
        read_table('a,b\n"1,2\n')


def test_quoted_header_names_work():
    table = read_table('"x, y",z\n1,2\n')
    assert table.columns == ("x, y", "z")
