import pytest
from exprtokens import TokenError, tokenize


@pytest.mark.parametrize("op", ["+", "-", "*", "/", "%", "^", "<", ">"])
def test_single_character_operators(op):
    assert tokenize(op) == [("OP", op, 0)]


@pytest.mark.parametrize("op", ["**", "//", "==", "!=", "<=", ">="])
def test_two_character_operators_are_one_token(op):
    assert tokenize(op) == [("OP", op, 0)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("* *", [("OP", "*", 0), ("OP", "*", 2)]),
        ("/ /", [("OP", "/", 0), ("OP", "/", 2)]),
        ("<>", [("OP", "<", 0), ("OP", ">", 1)]),
        ("***", [("OP", "**", 0), ("OP", "*", 2)]),
        ("////", [("OP", "//", 0), ("OP", "//", 2)]),
        ("<<", [("OP", "<", 0), ("OP", "<", 1)]),
        ("<=>", [("OP", "<=", 0), ("OP", ">", 2)]),
    ],
)
def test_longest_operator_wins_and_the_rest_is_tokenized_again(text, expected):
    assert tokenize(text) == expected


@pytest.mark.parametrize(
    ("text", "position"), [("< =", 2), ("=>", 0), ("<==", 2), ("=", 0), ("!", 0), ("a ! b", 2)]
)
def test_a_lone_equals_or_bang_is_an_error(text, position):
    with pytest.raises(TokenError) as info:
        tokenize(text)
    assert info.value.position == position


def test_operators_between_operands_need_no_spaces():
    assert tokenize("a**b//c") == [
        ("IDENT", "a", 0),
        ("OP", "**", 1),
        ("IDENT", "b", 3),
        ("OP", "//", 4),
        ("IDENT", "c", 6),
    ]


def test_comparison_chain():
    assert [t[:2] for t in tokenize("a<=b>=c==d!=e<f>g")] == [
        ("IDENT", "a"),
        ("OP", "<="),
        ("IDENT", "b"),
        ("OP", ">="),
        ("IDENT", "c"),
        ("OP", "=="),
        ("IDENT", "d"),
        ("OP", "!="),
        ("IDENT", "e"),
        ("OP", "<"),
        ("IDENT", "f"),
        ("OP", ">"),
        ("IDENT", "g"),
    ]


def test_power_and_unary_minus_are_separate_tokens():
    assert tokenize("2**-1") == [("NUM", "2", 0), ("OP", "**", 1), ("OP", "-", 3), ("NUM", "1", 4)]
    assert tokenize("a*-b") == [
        ("IDENT", "a", 0),
        ("OP", "*", 1),
        ("OP", "-", 2),
        ("IDENT", "b", 3),
    ]
