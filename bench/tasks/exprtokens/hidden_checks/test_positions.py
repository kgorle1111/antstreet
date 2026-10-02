import pytest
from exprtokens import tokenize


@pytest.mark.parametrize(("text", "kind"), [("(", "LPAREN"), (")", "RPAREN"), (",", "COMMA")])
def test_punctuation_kinds(text, kind):
    assert tokenize(text) == [(kind, text, 0)]


def test_positions_without_spaces():
    assert tokenize("2x+3") == [("NUM", "2", 0), ("IDENT", "x", 1), ("OP", "+", 2), ("NUM", "3", 3)]


def test_positions_with_spaces_count_the_skipped_characters():
    assert tokenize("  a  +   b ") == [("IDENT", "a", 2), ("OP", "+", 5), ("IDENT", "b", 9)]


def test_tabs_and_newlines_are_whitespace_and_count_in_positions():
    assert tokenize("a\n\tb\r\nc") == [("IDENT", "a", 0), ("IDENT", "b", 3), ("IDENT", "c", 6)]


def test_text_is_exactly_as_written():
    tokens = tokenize("Foo_1 + 2.50E+3")
    assert [t[1] for t in tokens] == ["Foo_1", "+", "2.50E+3"]


def test_a_function_call():
    assert tokenize("max(a, 2.5)") == [
        ("IDENT", "max", 0),
        ("LPAREN", "(", 3),
        ("IDENT", "a", 4),
        ("COMMA", ",", 5),
        ("NUM", "2.5", 7),
        ("RPAREN", ")", 10),
    ]


def test_parentheses_and_commas_do_not_merge():
    assert [t[0] for t in tokenize("((,))")] == ["LPAREN", "LPAREN", "COMMA", "RPAREN", "RPAREN"]
    assert [t[2] for t in tokenize("((,))")] == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("text", ["", " ", "   ", "\n", "\t\r\n ", " \n \n "])
def test_empty_or_blank_text_gives_no_tokens(text):
    assert tokenize(text) == []


def test_every_token_text_is_found_at_its_position():
    src = " sin(x1)**2 + .5e-3*(y_2 // 7) >= -z "
    for kind, text, position in tokenize(src):
        assert src[position : position + len(text)] == text
        assert kind in {"NUM", "IDENT", "OP", "LPAREN", "RPAREN", "COMMA"}


def test_tokens_are_tuples_in_a_list():
    result = tokenize("a")
    assert type(result) is list and type(result[0]) is tuple and len(result[0]) == 3
    assert type(result[0][2]) is int
