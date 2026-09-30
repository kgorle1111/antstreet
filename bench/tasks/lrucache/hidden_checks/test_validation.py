import pytest
from lrucache import LRUCache


@pytest.mark.parametrize("capacity", [0, -1, -50])
def test_capacity_below_one_raises(capacity):
    with pytest.raises(ValueError):
        LRUCache(capacity)


@pytest.mark.parametrize("ttl", [0, 0.0, -1, -0.5])
def test_non_positive_ttl_raises(ttl):
    with pytest.raises(ValueError):
        LRUCache(3, ttl=ttl)


def test_valid_arguments_are_accepted():
    LRUCache(1)
    LRUCache(1, ttl=None)
    LRUCache(10, ttl=0.001)
    LRUCache(10, ttl=60)
    LRUCache(3, ttl=5, clock=lambda: 0.0)


def test_clock_is_called_with_no_arguments():
    calls = []

    def clock():
        calls.append(1)
        return 0.0

    cache = LRUCache(2, ttl=5, clock=clock)
    cache.put("a", 1)
    assert cache.get("a") == 1
    assert calls
