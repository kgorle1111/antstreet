import pytest
from cidr4 import usable_hosts


@pytest.mark.parametrize(
    ("cidr", "count"),
    [
        ("10.0.0.0/24", 254),
        ("10.0.0.0/25", 126),
        ("10.0.0.128/25", 126),
        ("10.0.0.0/26", 62),
        ("10.0.0.0/29", 6),
        ("10.0.0.0/30", 2),
        ("10.0.0.0/31", 2),
        ("10.0.0.0/32", 1),
        ("10.0.0.1/32", 1),
        ("255.255.255.254/31", 2),
        ("255.255.255.255/32", 1),
        ("10.0.0.0/16", 65534),
        ("10.0.0.0/8", 16777214),
        ("128.0.0.0/1", 2147483646),
        ("0.0.0.0/0", 4294967294),
    ],
)
def test_usable_hosts(cidr, count):
    assert usable_hosts(cidr) == count
    assert type(usable_hosts(cidr)) is int


def test_the_count_is_the_size_minus_two_for_every_prefix_up_to_30():
    for prefix in range(0, 31):
        assert usable_hosts(f"0.0.0.0/{prefix}") == 2 ** (32 - prefix) - 2


def test_the_two_point_to_point_prefixes_are_special():
    assert usable_hosts("192.168.0.0/31") == 2
    assert usable_hosts("192.168.0.2/31") == 2
    assert usable_hosts("192.168.0.7/32") == 1
    assert usable_hosts("192.168.0.4/30") == 2


@pytest.mark.parametrize(
    "cidr", ["10.0.0.1/24", "10.0.0.0", "10.0.0.0/33", "", "10.0.0.0/", "x/8", "10.0.0.0/024"]
)
def test_a_bad_block_raises_value_error(cidr):
    with pytest.raises(ValueError):
        usable_hosts(cidr)


@pytest.mark.parametrize("value", [None, 24, b"10.0.0.0/24", ["10.0.0.0/24"]])
def test_a_value_that_is_not_a_str_raises_type_error(value):
    with pytest.raises(TypeError):
        usable_hosts(value)
