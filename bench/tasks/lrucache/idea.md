Create a Python module `lrucache.py` (standard library only) with one class:

    LRUCache(capacity: int, ttl: float | None = None, clock: Callable[[], float] = time.monotonic)

    get(key, default=None)
    put(key, value) -> None
    keys() -> list
    len(cache) -> int
    key in cache -> bool

It is a bounded key-value cache that evicts the least recently used entry and can expire entries
after a time to live. Keys are any hashable objects; values are any objects, including `None`.

1. `capacity` below 1 raises `ValueError`. A `ttl` that is given and not greater than 0 raises
   `ValueError`. `ttl=None` means entries never expire.
2. `clock` is a function taking no arguments that returns the current time in seconds. Every
   operation (`get`, `put`, `keys`, `len`, `in`) calls it to learn the current time. Tests pass a
   fake clock and never sleep.
3. An entry is written by `put`. It is live while `clock() - written_at < ttl` and expired from
   exactly `ttl` seconds after it was written onwards. Reading an entry with `get` or `in` does not
   extend its life; only `put` on the same key does.
4. An expired entry is gone: `get` returns the default for it, it is not in `keys()`, it does not
   count towards `len()`, `key in cache` is `False` for it, and it takes no capacity. Putting a
   key whose entry has expired inserts a new entry.
5. `get(key, default=None)` returns the value of a live entry and marks it the most recently
   used. For a missing or expired key it returns `default` and changes nothing. A stored `None`
   is a real value: `get` returns it, not `default`.
6. `put(key, value)` inserts a new entry or replaces the value of a live one. Either way the entry
   becomes the most recently used and its expiry restarts from the current time.
7. Inserting a new key when the cache already holds `capacity` live entries makes room by first
   removing every expired entry; only if the cache is still full is the least recently used live
   entry evicted, exactly one. Replacing the value of an existing live key never evicts anything.
   After any `put`, `len(cache)` is at most `capacity`.
8. `keys()` returns a new list of the live keys ordered from least recently used to most recently
   used. `len(cache)` is the number of live entries.
9. `key in cache` is `True` exactly when the key has a live entry. It does not change recency.
   Neither do `keys()` and `len()`.
