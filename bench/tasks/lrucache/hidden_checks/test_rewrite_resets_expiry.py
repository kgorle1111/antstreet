from lrucache import LRUCache


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_put_on_existing_key_restarts_expiry():
    clock = Clock()
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    clock.now = 8
    cache.put("a", 2)
    clock.now = 15
    assert cache.get("a") == 2
    clock.now = 17.9
    assert cache.get("a") == 2
    clock.now = 18
    assert cache.get("a") is None


def test_rewrite_of_one_key_does_not_restart_others():
    clock = Clock()
    cache = LRUCache(3, ttl=10, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    clock.now = 6
    cache.put("a", 3)
    clock.now = 10
    assert cache.get("b") is None
    assert cache.get("a") == 3
    assert cache.keys() == ["a"]


def test_repeated_rewrites_keep_an_entry_alive():
    clock = Clock()
    cache = LRUCache(2, ttl=10, clock=clock)
    for step in range(1, 8):
        cache.put("a", step)
        clock.now += 9
    assert cache.get("a") == 7
    clock.now += 1
    assert cache.get("a") is None


def test_replacing_an_expired_key_is_a_fresh_insert():
    clock = Clock()
    cache = LRUCache(2, ttl=10, clock=clock)
    cache.put("a", 1)
    cache.put("b", 2)
    clock.now = 10
    cache.put("a", 3)
    assert cache.keys() == ["a"]
    assert cache.get("b") is None
    clock.now = 19
    assert cache.get("a") == 3
