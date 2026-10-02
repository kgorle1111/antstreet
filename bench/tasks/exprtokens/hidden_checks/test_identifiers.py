import pytest
from exprtokens import TokenError, tokenize


@pytest.mark.parametrize(
    "name", ["x", "X", "_", "_x", "x1", "x_y", "foo_bar2", "__init__", "e", "E1"]
)
def test_identifiers(name):
    assert tokenize(name) == [("IDENT", name, 0)]


def test_digits_continue_an_identifier_but_cannot_start_one():
    assert tokenize("x1y2") == [("IDENT", "x1y2", 0)]
    assert tokenize("1x") == [("NUM", "1", 0), ("IDENT", "x", 1)]


def test_an_identifier_ends_at_an_operator_or_space():
    assert tokenize("ab+cd ef") == [
        ("IDENT", "ab", 0),
        ("OP", "+", 2),
        ("IDENT", "cd", 3),
        ("IDENT", "ef", 6),
    ]


def test_a_hyphen_ends_an_identifier():
    assert tokenize("a-b") == [("IDENT", "a", 0), ("OP", "-", 1), ("IDENT", "b", 2)]


def test_a_non_ascii_letter_is_an_error_at_its_position():
    for src, position in [("é", 0), ("abé", 2), ("x + π", 4), ("aéb", 1)]:
        with pytest.raises(TokenError) as info:
            tokenize(src)
        assert info.value.position == position


def test_non_ascii_digits_are_not_digits():
    with pytest.raises(TokenError) as info:
        tokenize("1 + ٣")
    assert info.value.position == 4
    with pytest.raises(TokenError) as info:
        tokenize("x٣")
    assert info.value.position == 1


def test_keyword_like_names_are_plain_identifiers():
    assert tokenize("and or not") == [("IDENT", "and", 0), ("IDENT", "or", 4), ("IDENT", "not", 7)]
