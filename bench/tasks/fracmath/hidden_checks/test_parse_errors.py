import pytest
from fracmath import parse_fraction


@pytest.mark.parametrize("text", ["", " ", "   ", "\t", "\n", " \t\n "])
def test_empty_or_whitespace_only_is_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize("text", ["1/0", "0/0", "5/0", "-1/0", "1 1/0", "10/00", "0 0/0"])
def test_a_zero_denominator_is_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize(
    "text",
    [
        "3/-4",
        "-3/-4",
        "+1/2",
        "+1",
        "1 -1/2",
        "1 +1/2",
        "--1",
        "-+1",
        "1-",
        "1/2-",
        "-",
        "1/-",
        "5/+2",
    ],
)
def test_a_sign_anywhere_but_the_very_front_is_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize("text", ["- 1/2", "-\t1/2", "- 5", "- 1 1/2", "-\n1"])
def test_whitespace_between_the_sign_and_the_digits_is_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize("text", ["1 / 2", "1/ 2", "1 /2", "1\t/\t2", "1 1 / 2", "1 1/ 2"])
def test_whitespace_around_the_slash_is_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize(
    "text",
    ["1.5", "0.5", "1.5/2", "1/2.5", "0.5/2", "1 1.5/2", "1.0", ".5", "5.", "1,5", "1e2", "1/2e1"],
)
def test_decimals_are_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize(
    "text",
    [
        "1/2/3",
        "1//2",
        "/2",
        "1/",
        "/",
        "1 1 1/2",
        "1 2",
        "1 1/2 1/2",
        "1/2 3/4",
        "1/2 3",
        "1 1/2/3",
        "1 /",
        "abc",
        "a/b",
        "1/b",
        "1 a/2",
        "one half",
        "1/2 abc",
        "(1/2)",
        "1_0/3",
        "0x10/3",
        "1/2!",
        "1 1/2;",
        "1/2\x00",
    ],
)
def test_other_text_is_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize("text", ["٣/٤", "١", "1/٢", "１/２", "1 １/２", "٣ 1/2"])
def test_non_ascii_digits_are_rejected(text):
    with pytest.raises(ValueError):
        parse_fraction(text)


@pytest.mark.parametrize("value", [None, 5, 0.5, b"1/2", ["1/2"], (1, 2), {"1/2"}])
def test_input_that_is_not_a_str_is_a_type_error(value):
    with pytest.raises(TypeError):
        parse_fraction(value)


def test_valid_text_still_parses_after_the_errors():
    assert parse_fraction("3/4") == (3, 4)
