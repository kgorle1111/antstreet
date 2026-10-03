import pytest
from cidr4 import parse_ip


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("0.0.0.0", 0),
        ("0.0.0.1", 1),
        ("0.0.1.0", 256),
        ("0.1.0.0", 65536),
        ("1.0.0.0", 16777216),
        ("10.0.0.1", 167772161),
        ("127.0.0.1", 2130706433),
        ("192.168.1.255", 3232236031),
        ("255.255.255.255", 4294967295),
        ("255.0.0.0", 4278190080),
        ("8.8.8.8", 134744072),
        ("100.200.50.25", 1690841625),
    ],
)
def test_valid_addresses(text, value):
    assert parse_ip(text) == value
    assert type(parse_ip(text)) is int


@pytest.mark.parametrize(
    "text", ["01.2.3.4", "1.02.3.4", "1.2.3.04", "00.0.0.0", "0.0.0.00", "007.1.1.1", "1.2.3.001"]
)
def test_leading_zeros_are_an_error(text):
    with pytest.raises(ValueError):
        parse_ip(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        "1",
        "1.2",
        "1.2.3",
        "1.2.3.4.5",
        "1.2.3.",
        ".1.2.3",
        "1..3.4",
        "....",
        "...",
        "1.2.3.4.",
    ],
)
def test_the_wrong_number_of_parts_is_an_error(text):
    with pytest.raises(ValueError):
        parse_ip(text)


@pytest.mark.parametrize(
    "text",
    [
        "256.1.1.1",
        "1.2.3.256",
        "999.1.1.1",
        "1.2.3.1000",
        "4294967295.0.0.0",
        "1.2.3.-1",
        "-1.2.3.4",
        "+1.2.3.4",
        "1.2.3.x",
        "a.b.c.d",
        "0x1.2.3.4",
        "1e1.2.3.4",
        "1.2.3.4a",
        "1_0.2.3.4",
        "1.2.3.4/24",
        "1.2.3.4:80",
    ],
)
def test_a_part_that_is_not_a_decimal_number_up_to_255_is_an_error(text):
    with pytest.raises(ValueError):
        parse_ip(text)


@pytest.mark.parametrize(
    "text",
    [" 1.2.3.4", "1.2.3.4 ", "1.2.3.4\n", "1. 2.3.4", "1.2.3. 4", "\t1.2.3.4", "1.2 .3.4"],
)
def test_spaces_are_not_ignored(text):
    with pytest.raises(ValueError):
        parse_ip(text)


@pytest.mark.parametrize(
    "text",
    [
        "1.2.3.\u0664",
        "\u0661.2.3.4",
        "1.2.3.\uff14",
        "\uff11.2.3.4",
        "1.2.3.\u00b2",
        "1.2.\u0969.4",
    ],
)
def test_digits_of_other_scripts_are_an_error(text):
    with pytest.raises(ValueError):
        parse_ip(text)


@pytest.mark.parametrize("value", [None, 5, b"1.2.3.4", ["1.2.3.4"], 1.5])
def test_a_value_that_is_not_a_str_raises_type_error(value):
    with pytest.raises(TypeError):
        parse_ip(value)
