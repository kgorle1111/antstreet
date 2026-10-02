import math
import time
from collections import OrderedDict

from bucket import TokenBucket


def _check_key(key):
    if key is None:
        raise ValueError("key must not be None")


def _check_cost(cost):
    if not cost > 0:
        raise ValueError("cost must be greater than 0")


class RateLimiter:
    def __init__(self, capacity, refill_rate, clock=time.monotonic, max_keys=None):
        TokenBucket(capacity, refill_rate, clock)
        if max_keys is not None and (
            isinstance(max_keys, bool) or not isinstance(max_keys, int) or max_keys < 1
        ):
            raise ValueError("max_keys must be None or an int of at least 1")
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._clock = clock
        self._max_keys = max_keys
        self._buckets = OrderedDict()

    def allow(self, key, cost=1):
        _check_key(key)
        _check_cost(cost)
        if key in self._buckets:
            self._buckets.move_to_end(key)
        else:
            if self._max_keys is not None and len(self._buckets) >= self._max_keys:
                self._buckets.popitem(last=False)
            self._buckets[key] = TokenBucket(self._capacity, self._refill_rate, self._clock)
        return self._buckets[key].try_acquire(cost)

    def remaining(self, key):
        _check_key(key)
        bucket = self._buckets.get(key)
        return bucket.available() if bucket else float(self._capacity)

    def retry_after(self, key, cost=1):
        _check_key(key)
        _check_cost(cost)
        bucket = self._buckets.get(key)
        if bucket:
            return bucket.retry_after(cost)
        return 0.0 if cost <= self._capacity else math.inf

    def reset(self, key):
        _check_key(key)
        return self._buckets.pop(key, None) is not None

    def keys(self):
        return list(self._buckets)

    def __len__(self):
        return len(self._buckets)

    def __contains__(self, key):
        return key in self._buckets
