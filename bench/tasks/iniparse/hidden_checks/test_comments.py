from iniparse import parse_ini


def test_semicolon_and_hash_lines_are_skipped():
    text = "; top comment\n# another\n[a]\n; inside\nk = v\n# trailing\n"
    assert parse_ini(text) == {"a": {"k": "v"}}


def test_indented_comment_lines_are_still_comments():
    assert parse_ini("[a]\n   ; indented\n\t# tabbed\nk=v") == {"a": {"k": "v"}}


def test_a_comment_line_that_looks_like_a_key_or_header_is_skipped():
    assert parse_ini("[a]\n; k = v\n# [b]\nz = 1") == {"a": {"z": "1"}}


def test_there_are_no_inline_comments_in_values():
    assert parse_ini("[a]\nk = b ; c\nj = x # y") == {"a": {"k": "b ; c", "j": "x # y"}}


def test_comment_characters_inside_a_line_do_not_start_a_comment_in_keys_or_headers():
    assert parse_ini("[a#b]\nk;1 = v") == {"a#b": {"k;1": "v"}}


def test_a_file_of_only_comments_is_empty():
    assert parse_ini("; one\n# two\n") == {}
