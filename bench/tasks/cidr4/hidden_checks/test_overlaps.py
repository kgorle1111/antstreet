import pytest
from cidr4 import overlaps


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("10.0.0.0/24", "10.0.0.0/24", True),
        ("10.0.0.0/8", "10.1.0.0/16", True),
        ("10.0.0.0/8", "10.255.255.255/32", True),
        ("10.0.0.0/8", "10.0.0.0/32", True),
        ("10.0.0.0/24", "10.0.0.128/25", True),
        ("10.0.0.128/25", "10.0.0.0/24", True),
        ("10.0.0.0/25", "10.0.0.128/25", False),
        ("10.0.0.128/25", "10.0.0.0/25", False),
        ("10.0.0.0/24", "10.0.1.0/24", False),
        ("10.0.1.0/24", "10.0.0.0/24", False),
        ("10.0.0.0/24", "10.0.2.0/24", False),
        ("10.0.0.0/8", "11.0.0.0/8", False),
        ("10.0.0.0/8", "9.0.0.0/8", False),
        ("10.0.0.0/8", "172.16.0.0/12", False),
        ("0.0.0.0/0", "10.1.2.3/32", True),
        ("0.0.0.0/0", "0.0.0.0/0", True),
        ("0.0.0.0/0", "255.255.255.255/32", True),
        ("10.0.0.5/32", "10.0.0.5/32", True),
        ("10.0.0.5/32", "10.0.0.6/32", False),
        ("10.0.0.5/32", "10.0.0.4/32", False),
        ("255.255.255.255/32", "255.255.255.254/31", True),
        ("255.255.255.254/32", "255.255.255.255/32", False),
        ("0.0.0.0/32", "0.0.0.1/32", False),
        ("192.168.0.0/16", "192.168.255.0/24", True),
        ("192.168.0.0/16", "192.169.0.0/24", False),
        ("192.168.0.0/16", "192.167.255.0/24", False),
    ],
)
def test_overlap_of_two_blocks(a, b, expected):
    assert overlaps(a, b) is expected


def test_the_result_does_not_depend_on_the_order():
    blocks = [
        "10.0.0.0/8",
        "10.1.0.0/16",
        "10.1.1.0/24",
        "11.0.0.0/8",
        "10.0.0.0/24",
        "0.0.0.0/0",
        "10.1.1.1/32",
        "192.168.0.0/16",
    ]
    for a in blocks:
        for b in blocks:
            assert overlaps(a, b) is overlaps(b, a), (a, b)


def test_halves_of_the_address_space_and_their_neighbours():
    assert overlaps("128.0.0.0/1", "0.0.0.0/1") is False
    assert overlaps("128.0.0.0/1", "128.0.0.0/1") is True
    assert overlaps("192.0.0.0/2", "128.0.0.0/2") is False
    assert overlaps("64.0.0.0/2", "0.0.0.0/1") is True
    assert overlaps("192.0.0.0/2", "0.0.0.0/1") is False
    assert overlaps("64.0.0.0/2", "0.0.0.0/0") is True


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("10.0.0.1/24", "10.0.0.0/24"),
        ("10.0.0.0/24", "10.0.0.1/24"),
        ("10.0.0.0", "10.0.0.0/24"),
        ("10.0.0.0/24", "x"),
        ("10.0.0.0/24", ""),
    ],
)
def test_a_bad_block_raises_value_error(a, b):
    with pytest.raises(ValueError):
        overlaps(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [(None, "10.0.0.0/24"), ("10.0.0.0/24", None), (5, 5), ("10.0.0.0/24", b"10.0.0.0/24")],
)
def test_arguments_that_are_not_str_raise_type_error(a, b):
    with pytest.raises(TypeError):
        overlaps(a, b)
