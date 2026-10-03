import pytest
from cidr4 import parse_cidr


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10.0.0.0/24", (167772160, 24)),
        ("10.0.0.0/8", (167772160, 8)),
        ("0.0.0.0/0", (0, 0)),
        ("0.0.0.0/32", (0, 32)),
        ("10.0.0.1/32", (167772161, 32)),
        ("192.168.0.0/16", (3232235520, 16)),
        ("192.168.1.128/25", (3232235904, 25)),
        ("255.255.255.255/32", (4294967295, 32)),
        ("255.255.255.254/31", (4294967294, 31)),
        ("128.0.0.0/1", (2147483648, 1)),
        ("172.16.0.0/12", (2886729728, 12)),
    ],
)
def test_valid_blocks(text, expected):
    assert parse_cidr(text) == expected
    assert type(parse_cidr(text)) is tuple
    assert all(type(x) is int for x in parse_cidr(text))


@pytest.mark.parametrize(
    "text",
    [
        "10.0.0.1/24",
        "10.0.0.255/24",
        "10.0.1.0/23",
        "0.0.0.1/0",
        "128.0.0.0/0",
        "10.0.0.1/31",
        "255.255.255.255/31",
        "10.1.0.0/8",
    ],
)
def test_strict_rejects_host_bits(text):
    with pytest.raises(ValueError):
        parse_cidr(text)
    with pytest.raises(ValueError):
        parse_cidr(text, strict=True)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10.0.0.77/24", (167772160, 24)),
        ("10.0.0.255/24", (167772160, 24)),
        ("10.1.2.3/8", (167772160, 8)),
        ("255.255.255.255/0", (0, 0)),
        ("255.255.255.255/31", (4294967294, 31)),
        ("10.0.0.1/32", (167772161, 32)),
        ("10.0.0.0/24", (167772160, 24)),
        ("192.168.1.129/25", (3232235904, 25)),
    ],
)
def test_non_strict_clears_the_host_bits(text, expected):
    assert parse_cidr(text, strict=False) == expected


@pytest.mark.parametrize(
    "text",
    ["10.0.0.0", "10.0.0.0/", "/24", "/", "", "10.0.0.0//24", "10.0.0.0/24/24", "10.0.0.0/2/4"],
)
def test_the_slash_and_both_parts_are_required(text):
    with pytest.raises(ValueError):
        parse_cidr(text)
    with pytest.raises(ValueError):
        parse_cidr(text, strict=False)


@pytest.mark.parametrize(
    "prefix",
    [
        "33",
        "64",
        "100",
        "255",
        "-1",
        "+8",
        "08",
        "00",
        "024",
        "8.0",
        "x",
        "8 ",
        " 8",
        "\u0668",
        "\uff18",
        "1e1",
        "0x8",
    ],
)
def test_a_bad_prefix_is_an_error(prefix):
    with pytest.raises(ValueError):
        parse_cidr(f"10.0.0.0/{prefix}")
    with pytest.raises(ValueError):
        parse_cidr(f"10.0.0.0/{prefix}", strict=False)


@pytest.mark.parametrize("prefix", ["0", "1", "9", "10", "31", "32"])
def test_prefixes_0_to_32_are_read(prefix):
    assert parse_cidr(f"0.0.0.0/{prefix}", strict=False)[1] == int(prefix)


@pytest.mark.parametrize(
    "text", ["256.0.0.0/8", "1.2.3/24", "01.0.0.0/8", " 10.0.0.0/8", "10.0.0.0/8 ", "a.b.c.d/8"]
)
def test_a_bad_address_is_an_error(text):
    with pytest.raises(ValueError):
        parse_cidr(text, strict=False)


@pytest.mark.parametrize("value", [None, 5, b"10.0.0.0/8", ["10.0.0.0/8"]])
def test_a_value_that_is_not_a_str_raises_type_error(value):
    with pytest.raises(TypeError):
        parse_cidr(value)
