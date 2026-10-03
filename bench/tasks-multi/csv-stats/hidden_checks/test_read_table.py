import dataclasses

import pytest
from reader import Table, read_table


def test_header_and_rows():
    table = read_table("a,b,c\n1,2,3\n4,5,6\n")
    assert isinstance(table, Table)
    assert table.columns == ("a", "b", "c")
    assert table.rows == (("1", "2", "3"), ("4", "5", "6"))
    assert len(table) == 2


def test_header_only_is_a_valid_empty_table():
    table = read_table("a,b\n")
    assert table.columns == ("a", "b")
    assert table.rows == ()
    assert len(table) == 0
    assert table.column("a") == []
    assert table.numbers("b") == []


def test_no_trailing_newline_and_all_line_endings():
    expected = (("1", "2"), ("3", "4"))
    for text in ("a,b\n1,2\n3,4", "a,b\r\n1,2\r\n3,4\r\n", "a,b\r1,2\r3,4\r", "a,b\n1,2\r\n3,4"):
        table = read_table(text)
        assert table.columns == ("a", "b")
        assert table.rows == expected


def test_quoted_fields():
    table = read_table('name,note\n"Smith, Ann","said ""hi"""\n"multi\nline",x\n')
    assert table.rows == (("Smith, Ann", 'said "hi"'), ("multi\nline", "x"))


def test_values_are_kept_exactly():
    table = read_table("a,b\n  x ,\t\n,\n")
    assert table.rows == (("  x ", "\t"), ("", ""))


def test_header_names_are_stripped_but_not_case_folded():
    table = read_table(" Name , AGE\nAnn,3\n")
    assert table.columns == ("Name", "AGE")
    assert table.column("Name") == ["Ann"]


def test_byte_order_mark_is_removed():
    table = read_table("﻿a,b\n1,2\n")
    assert table.columns == ("a", "b")


def test_blank_lines_are_skipped_but_a_quoted_empty_field_is_a_row():
    table = read_table("\n\na\n\n1\n\n2\n")
    assert table.columns == ("a",)
    assert table.rows == (("1",), ("2",))
    table = read_table('a\n""\n1\n')
    assert table.rows == (("",), ("1",))


def test_a_line_of_spaces_is_not_blank():
    table = read_table("a\n \n1\n")
    assert table.rows == ((" ",), ("1",))
    with pytest.raises(ValueError):
        read_table("a,b\n \n")


def test_table_is_a_frozen_value():
    table = read_table("a\n1\n")
    with pytest.raises(dataclasses.FrozenInstanceError):
        table.columns = ("z",)
    assert table == read_table("a\n1\n")


def test_unicode_and_wide_tables():
    table = read_table("näme,价格\nJosé,\U0001f600\n")
    assert table.columns == ("näme", "价格")
    assert table.rows == (("José", "\U0001f600"),)
    wide = read_table(",".join(f"c{i}" for i in range(50)) + "\n" + ",".join("x" * 50) + "\n")
    assert len(wide.columns) == 50 and len(wide.rows[0]) == 50
