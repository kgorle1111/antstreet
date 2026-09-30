from lrucache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_entry_is_live_just_before_ttl():
    clock = Clock(100.0)
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 109.5
    assert cache.get("a") == 1


def test_entry_is_expired_at_exactly_ttl():
    clock = Clock(100.0)
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 110.0
    assert cache.get("a") is None
    assert cache.get("a", "gone") == "gone"


def test_expired_entries_leave_len_and_keys():
    clock = Clock()
    cache = LRUCache(5, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 4
    cache.put("b", 2)
    clock.now = 8
    cache.put("c", 3)
    assert len(cache) == 3
    clock.now = 10
    assert len(cache) == 2
    assert cache.keys() == ["b", "c"]
    clock.now = 14
    assert len(cache) == 1
    assert cache.keys() == ["c"]
    clock.now = 18
    assert len(cache) == 0
    assert cache.keys() == []


def test_get_does_not_extend_life():
    clock = Clock()
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 6
    assert cache.get("a") == 1
    clock.now = 11
    assert cache.get("a") is None


def test_without_ttl_nothing_expires():
    clock = Clock()
    cache = LRUCache(3, clock=clock)
    cache.put("a", 1)
    clock.now = 10.0**9
    assert cache.get("a") == 1
    assert len(cache) == 1
    assert "a" in cache


def test_expiry_is_per_entry():
    clock = Clock()
    cache = LRUCache(3, ttl=5, clock=clock)
    cache.put("old", 1)
    clock.now = 3
    cache.put("new", 2)
    clock.now = 6
    assert cache.get("old") is None
    assert cache.get("new") == 2


def test_expired_key_can_be_put_again():
    clock = Clock()
    cache = LRUCache(3, ttl=5, clock=clock)
    cache.put("a", 1)
    clock.now = 5
    assert cache.get("a") is None
    cache.put("a", 2)
    assert cache.get("a") == 2
    assert len(cache) == 1
    assert cache.keys() == ["a"]
