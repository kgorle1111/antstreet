import pytest
from cidr4 import format_cidr, parse_cidr


@pytest.mark.parametrize(
    ("address", "prefix", "text"),
    [
        (167772160, 24, "10.0.0.0/24"),
        (167772160, 8, "10.0.0.0/8"),
        (0, 0, "0.0.0.0/0"),
        (0, 32, "0.0.0.0/32"),
        (4294967295, 32, "255.255.255.255/32"),
        (4294967294, 31, "255.255.255.254/31"),
        (3232235904, 25, "192.168.1.128/25"),
        (167772161, 32, "10.0.0.1/32"),
        (2147483648, 1, "128.0.0.0/1"),
        (16909060, 32, "1.2.3.4/32"),
    ],
)
def test_known_blocks(address, prefix, text):
    assert format_cidr(address, prefix) == text


@pytest.mark.parametrize(
    "text",
    ["10.0.0.0/24", "0.0.0.0/0", "192.168.1.128/25", "1.2.3.4/32", "172.16.0.0/12", "8.8.8.8/32"],
)
def test_format_undoes_parse(text):
    assert format_cidr(*parse_cidr(text)) == text


@pytest.mark.parametrize(
    ("address", "prefix"),
    [
        (-1, 24),
        (4294967296, 0),
        (2**40, 8),
        (0, -1),
        (0, 33),
        (167772160, 33),
        (167772161, 24),  # host bit set
        (167772160, 3),  # 10.0.0.0 has bits set below /3
        (1, 31),
        (4294967295, 24),
        (4294967295, 0),
    ],
)
def test_out_of_range_or_host_bits_raise_value_error(address, prefix):
    with pytest.raises(ValueError):
        format_cidr(address, prefix)


@pytest.mark.parametrize(
    ("address", "prefix"),
    [
        ("10.0.0.0", 24),
        (167772160, "24"),
        (None, 24),
        (167772160, None),
        (1.5, 24),
        (167772160, 24.0),
        (b"1", 8),
    ],
)
def test_arguments_that_are_not_ints_raise_type_error(address, prefix):
    with pytest.raises(TypeError):
        format_cidr(address, prefix)


def test_the_largest_address_and_block_edges_round_trip():
    for prefix in range(0, 33):
        address = (2**32 - 1) & ~((2**32 - 1) >> prefix)
        text = format_cidr(address, prefix)
        assert parse_cidr(text) == (address, prefix)
        assert text.endswith(f"/{prefix}")
    assert format_cidr(0, 0) == "0.0.0.0/0"
