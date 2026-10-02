import pytest
from exprtokens import TokenError, tokenize


@pytest.mark.parametrize(
    ("src", "position"),
    [
        ("$", 0),
        ("1 $ 2", 2),
        ("a # b", 2),
        ("x = 1", 2),
        ("x!", 1),
        ("5.", 1),
        ("1.5.", 3),
        ("5.x", 1),
        ("a.b", 1),
        ("  ?", 2),
        ("f(x);", 4),
        ("a @ b @ c", 2),
        ("'q'", 0),
        ('1 + "s"', 4),
        ("a b", 1),
        ("{}", 0),
        ("a & b", 2),
        ("a | b", 2),
        ("a~b", 1),
        ("2 ** 3 ?", 7),
    ],
)
def test_the_error_position_is_the_first_bad_character(src, position):
    with pytest.raises(TokenError) as info:
        tokenize(src)
    assert info.value.position == position
    assert type(info.value.position) is int


def test_token_error_is_a_value_error():
    assert issubclass(TokenError, ValueError)
    with pytest.raises(ValueError):
        tokenize("1 $ 2")


def test_only_the_first_error_is_reported():
    with pytest.raises(TokenError) as info:
        tokenize("a $ b $ c")
    assert info.value.position == 2


def test_tokens_before_a_late_error_do_not_prevent_it():
    with pytest.raises(TokenError) as info:
        tokenize("1 + 2 * (3 - 4) / 5 ?")
    assert info.value.position == 20


def test_a_dot_before_a_digit_starts_a_number_instead_of_failing():
    assert [t[:2] for t in tokenize("a.5")] == [("IDENT", "a"), ("NUM", ".5")]


@pytest.mark.parametrize("bad", [None, 5, b"1+2", ["1", "+", "2"], 1.5])
def test_non_string_argument_raises_a_plain_value_error(bad):
    with pytest.raises(ValueError) as info:
        tokenize(bad)
    assert not isinstance(info.value, TokenError)
