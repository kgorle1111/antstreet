from lrucache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_keys_run_from_least_to_most_recently_used():
    cache = LRUCache(3, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.keys() == ["a", "b", "c"]


def test_evicts_least_recently_used_when_full():
    cache = LRUCache(2, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.keys() == ["b", "c"]
    assert cache.get("a") is None
    assert len(cache) == 2


def test_get_marks_most_recently_used():
    cache = LRUCache(3, clock=Clock())
    for key in "abc":
        cache.put(key, key)
    assert cache.get("a") == "a"
    assert cache.keys() == ["b", "c", "a"]
    cache.put("d", "d")
    assert cache.keys() == ["c", "a", "d"]


def test_missing_get_changes_nothing():
    cache = LRUCache(2, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("zzz") is None
    assert cache.keys() == ["a", "b"]


def test_put_on_existing_key_marks_most_recently_used():
    cache = LRUCache(3, clock=Clock())
    for key in "abc":
        cache.put(key, 1)
    cache.put("a", 2)
    assert cache.keys() == ["b", "c", "a"]
    cache.put("d", 1)
    assert cache.keys() == ["c", "a", "d"]


def test_replacing_a_key_in_a_full_cache_evicts_nothing():
    cache = LRUCache(2, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("b", 20)
    cache.put("a", 10)
    assert len(cache) == 2
    assert cache.get("a") == 10
    assert cache.get("b") == 20


def test_capacity_one():
    cache = LRUCache(1, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.keys() == ["b"]
    assert cache.get("a") is None
    cache.put("b", 3)
    assert cache.get("b") == 3
    assert len(cache) == 1


def test_many_inserts_never_exceed_capacity():
    cache = LRUCache(5, clock=Clock())
    for i in range(50):
        cache.put(i, i)
        assert len(cache) <= 5
    assert cache.keys() == [45, 46, 47, 48, 49]
