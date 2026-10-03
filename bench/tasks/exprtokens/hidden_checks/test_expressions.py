from exprtokens import tokenize


def kinds_and_texts(src):
    return [(kind, text) for kind, text, _ in tokenize(src)]


def test_a_simple_sum():
    assert tokenize("1 + 2") == [("NUM", "1", 0), ("OP", "+", 2), ("NUM", "2", 4)]


def test_precedence_expression():
    assert kinds_and_texts("a + b * (c - 1) ** 2") == [
        ("IDENT", "a"),
        ("OP", "+"),
        ("IDENT", "b"),
        ("OP", "*"),
        ("LPAREN", "("),
        ("IDENT", "c"),
        ("OP", "-"),
        ("NUM", "1"),
        ("RPAREN", ")"),
        ("OP", "**"),
        ("NUM", "2"),
    ]


def test_scientific_notation_in_an_expression():
    assert kinds_and_texts("1e3*x+2.5e-2") == [
        ("NUM", "1e3"),
        ("OP", "*"),
        ("IDENT", "x"),
        ("OP", "+"),
        ("NUM", "2.5e-2"),
    ]


def test_nested_calls_and_unary_minus():
    assert kinds_and_texts("-f(g(-x), 3)") == [
        ("OP", "-"),
        ("IDENT", "f"),
        ("LPAREN", "("),
        ("IDENT", "g"),
        ("LPAREN", "("),
        ("OP", "-"),
        ("IDENT", "x"),
        ("RPAREN", ")"),
        ("COMMA", ","),
        ("NUM", "3"),
        ("RPAREN", ")"),
    ]


def test_a_condition_with_comparisons():
    assert kinds_and_texts("x>=10 != y<2") == [
        ("IDENT", "x"),
        ("OP", ">="),
        ("NUM", "10"),
        ("OP", "!="),
        ("IDENT", "y"),
        ("OP", "<"),
        ("NUM", "2"),
    ]


def test_floor_division_and_modulo_and_power_operators():
    assert kinds_and_texts("7//2%3^2") == [
        ("NUM", "7"),
        ("OP", "//"),
        ("NUM", "2"),
        ("OP", "%"),
        ("NUM", "3"),
        ("OP", "^"),
        ("NUM", "2"),
    ]


def test_a_long_expression_is_tokenized_in_order():
    src = " + ".join(f"x{i}" for i in range(200))
    tokens = tokenize(src)
    assert len(tokens) == 399
    assert tokens[0] == ("IDENT", "x0", 0)
    assert tokens[-1][:2] == ("IDENT", "x199")
    assert [t[2] for t in tokens] == sorted(t[2] for t in tokens)


def test_tokenizing_the_joined_token_texts_gives_the_same_kinds():
    src = "f(a, 1.5e3) ** -2 // b2 >= .5"
    tokens = tokenize(src)
    again = tokenize(" ".join(text for _, text, _ in tokens))
    assert [t[:2] for t in again] == [t[:2] for t in tokens]
