from lrucache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_expired_entry_is_removed_before_a_live_lru_entry_is_evicted():
    clock = Clock()
    cache = LRUCache(2, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 5
    cache.put("b", 2)
    assert cache.get("a") == 1  # order is now b, a; "a" was written at 0
    clock.now = 12  # "a" is expired, "b" is live and is the least recently used
    cache.put("c", 3)
    assert cache.keys() == ["b", "c"]
    assert cache.get("b") == 2


def test_expired_entries_take_no_capacity():
    clock = Clock()
    cache = LRUCache(2, ttl=10, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    clock.now = 10
    cache.put("c", 3)
    cache.put("d", 4)
    assert cache.keys() == ["c", "d"]


def test_only_one_live_entry_is_evicted():
    clock = Clock()
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 4
    cache.put("b", 2)
    cache.put("c", 3)
    clock.now = 10
    cache.put("d", 4)  # "a" expired; room already, nothing live is evicted
    assert cache.keys() == ["b", "c", "d"]
    cache.put("e", 5)  # full of live entries: exactly the LRU goes
    assert cache.keys() == ["c", "d", "e"]


def test_full_cache_of_live_entries_evicts_lru_even_with_ttl():
    clock = Clock()
    cache = LRUCache(2, ttl=100, clock=clock)
    cache.put("a", 1)
    clock.now = 1
    cache.put("b", 2)
    clock.now = 2
    cache.put("c", 3)
    assert cache.keys() == ["b", "c"]


def test_all_expired_then_insert_leaves_only_the_new_entry():
    clock = Clock()
    cache = LRUCache(3, ttl=5, clock=clock)
    for key in "abc":
        cache.put(key, key)
    clock.now = 50
    cache.put("z", "z")
    assert cache.keys() == ["z"]
    assert len(cache) == 1
