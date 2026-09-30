from lrucache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_contains_reports_live_entries():
    cache = LRUCache(3, clock=Clock())
    cache.put("a", 1)
    assert "a" in cache
    assert "b" not in cache


def test_contains_does_not_change_recency():
    cache = LRUCache(2, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    assert "a" in cache
    assert cache.keys() == ["a", "b"]
    cache.put("c", 3)
    assert cache.keys() == ["b", "c"]
    assert "a" not in cache


def test_keys_and_len_do_not_change_recency():
    cache = LRUCache(3, clock=Clock())
    for key in "abc":
        cache.put(key, key)
    cache.keys()
    len(cache)
    cache.keys()
    assert cache.keys() == ["a", "b", "c"]
    cache.put("d", "d")
    assert cache.keys() == ["b", "c", "d"]


def test_contains_is_false_once_expired():
    clock = Clock()
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 9
    assert "a" in cache
    clock.now = 10
    assert "a" not in cache


def test_contains_does_not_extend_life():
    clock = Clock()
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 6
    assert "a" in cache
    clock.now = 12
    assert "a" not in cache
