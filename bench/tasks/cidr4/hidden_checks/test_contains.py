import pytest
from cidr4 import contains


@pytest.mark.parametrize(
    ("cidr", "ip", "expected"),
    [
        ("10.0.0.0/24", "10.0.0.0", True),
        ("10.0.0.0/24", "10.0.0.1", True),
        ("10.0.0.0/24", "10.0.0.128", True),
        ("10.0.0.0/24", "10.0.0.255", True),
        ("10.0.0.0/24", "10.0.1.0", False),
        ("10.0.0.0/24", "10.0.1.255", False),
        ("10.0.1.0/24", "10.0.0.255", False),
        ("10.0.0.0/24", "9.255.255.255", False),
        ("10.0.0.0/24", "11.0.0.0", False),
        ("10.0.0.0/8", "10.255.255.255", True),
        ("10.0.0.0/8", "10.0.0.0", True),
        ("10.0.0.0/8", "11.0.0.0", False),
        ("10.0.0.0/8", "9.255.255.255", False),
        ("192.168.1.128/25", "192.168.1.127", False),
        ("192.168.1.128/25", "192.168.1.128", True),
        ("192.168.1.128/25", "192.168.1.255", True),
        ("192.168.1.128/25", "192.168.2.0", False),
        ("10.0.0.5/32", "10.0.0.5", True),
        ("10.0.0.5/32", "10.0.0.4", False),
        ("10.0.0.5/32", "10.0.0.6", False),
        ("0.0.0.0/32", "0.0.0.0", True),
        ("255.255.255.255/32", "255.255.255.255", True),
        ("255.255.255.255/32", "255.255.255.254", False),
        ("0.0.0.0/0", "0.0.0.0", True),
        ("0.0.0.0/0", "255.255.255.255", True),
        ("0.0.0.0/0", "8.8.8.8", True),
        ("255.255.255.254/31", "255.255.255.254", True),
        ("255.255.255.254/31", "255.255.255.255", True),
        ("255.255.255.254/31", "255.255.255.253", False),
        ("128.0.0.0/1", "255.255.255.255", True),
        ("128.0.0.0/1", "127.255.255.255", False),
    ],
)
def test_membership_including_first_and_last_address(cidr, ip, expected):
    assert contains(cidr, ip) is expected


def test_every_address_of_a_small_block_and_its_neighbours():
    inside = {f"10.0.0.{n}" for n in range(64, 128)}
    for n in range(0, 256):
        ip = f"10.0.0.{n}"
        assert contains("10.0.0.64/26", ip) is (ip in inside), ip


def test_a_block_does_not_contain_an_address_of_a_different_block_with_the_same_host_part():
    assert contains("10.0.0.0/24", "11.0.0.5") is False
    assert contains("10.0.0.0/24", "10.1.0.5") is False
    assert contains("10.0.0.0/24", "10.0.5.5") is False


@pytest.mark.parametrize(
    "cidr", ["10.0.0.1/24", "10.0.0.0", "10.0.0.0/33", "x/8", "", "10.0.0.0/08"]
)
def test_a_bad_block_raises_value_error(cidr):
    with pytest.raises(ValueError):
        contains(cidr, "10.0.0.1")


@pytest.mark.parametrize("ip", ["10.0.0", "10.0.0.256", "", "10.0.0.0/24", "01.0.0.0", " 10.0.0.1"])
def test_a_bad_address_raises_value_error(ip):
    with pytest.raises(ValueError):
        contains("10.0.0.0/24", ip)


@pytest.mark.parametrize(
    ("cidr", "ip"),
    [
        (None, "10.0.0.1"),
        ("10.0.0.0/24", None),
        (5, "10.0.0.1"),
        ("10.0.0.0/24", 167772161),
        (b"10.0.0.0/24", "10.0.0.1"),
    ],
)
def test_arguments_that_are_not_str_raise_type_error(cidr, ip):
    with pytest.raises(TypeError):
        contains(cidr, ip)
