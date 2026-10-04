import pytest
from baseconv import convert, parse_number

NOT_A_NUMBER = [
    "",
    "-",
    ".",
    "-.",
    "1.",
    ".5",
    "-.5",
    "1..2",
    "1.2.3",
    " 1",
    "1 ",
    " 1 ",
    "1 2",
    "\n1",
    "1\n",
    "\t1",
    "+1",
    "--1",
    "-+1",
    "+-1",
    "1-",
    "1-2",
    "1_000",
    "1e5",
    "0x10",
    "1,5",
    "1/2",
    "٣",  # an Arabic-Indic digit is not a digit here
    "１",  # a full-width digit is not a digit here
    "1.２",
    "é",
    "1.5.",
    "-1.-5",
    "- 1",
]


@pytest.mark.parametrize("text", NOT_A_NUMBER)
def test_text_that_is_not_a_number_raises_value_error(text):
    with pytest.raises(ValueError):
        parse_number(text, 10)
    with pytest.raises(ValueError):
        convert(text, 10, 2)


@pytest.mark.parametrize(
    ("text", "base"),
    [
        ("2", 2),
        ("1.2", 2),
        ("9", 8),
        ("8.1", 8),
        ("g", 16),
        ("f.g", 16),
        ("a", 10),
        ("1.a", 10),
        ("z", 35),
        ("Z", 35),
        ("10.5", 5),
        ("-3", 3),
        ("0.9", 9),
        ("12", 2),
    ],
)
def test_a_digit_not_smaller_than_the_base_raises_value_error(text, base):
    with pytest.raises(ValueError):
        parse_number(text, base)
    with pytest.raises(ValueError):
        convert(text, base, 10)


def test_the_largest_digit_of_each_base_is_accepted():
    assert parse_number("1", 2) == 1
    assert parse_number("7", 8) == 7
    assert parse_number("9", 10) == 9
    assert parse_number("f", 16) == 15
    assert parse_number("z", 36) == 35
    assert parse_number("y", 35) == 34


@pytest.mark.parametrize("bad", [None, 5, b"10", 1.5, ["1"], ("1",), True])
def test_text_that_is_not_a_str_raises_type_error(bad):
    with pytest.raises(TypeError):
        parse_number(bad, 10)
    with pytest.raises(TypeError):
        convert(bad, 10, 2)
