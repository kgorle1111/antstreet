from lrucache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_put_then_get():
    cache = LRUCache(3, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    assert cache.get("b") == 2
    assert len(cache) == 2


def test_missing_key_returns_default():
    cache = LRUCache(3, clock=Clock())
    assert cache.get("nope") is None
    assert cache.get("nope", "fallback") == "fallback"
    assert len(cache) == 0
    assert cache.keys() == []


def test_put_replaces_value_without_growing():
    cache = LRUCache(3, clock=Clock())
    cache.put("a", 1)
    cache.put("a", 2)
    assert cache.get("a") == 2
    assert len(cache) == 1
    assert cache.keys() == ["a"]


def test_stored_none_is_a_real_value():
    cache = LRUCache(3, clock=Clock())
    cache.put("a", None)
    assert cache.get("a", "fallback") is None
    assert "a" in cache
    assert len(cache) == 1


def test_falsy_values_and_non_string_keys():
    cache = LRUCache(4, clock=Clock())
    cache.put(0, 0)
    cache.put((1, 2), "")
    cache.put("x", [])
    assert cache.get(0, "d") == 0
    assert cache.get((1, 2), "d") == ""
    assert cache.get("x", "d") == []


def test_keys_returns_a_copy():
    cache = LRUCache(3, clock=Clock())
    cache.put("a", 1)
    snapshot = cache.keys()
    snapshot.append("zzz")
    snapshot.clear()
    assert cache.keys() == ["a"]
    assert len(cache) == 1


def test_default_clock_works_without_injection():
    cache = LRUCache(2)
    cache.put("a", 1)
    assert cache.get("a") == 1
    cache = LRUCache(2, ttl=3600)
    cache.put("a", 1)
    assert cache.get("a") == 1
