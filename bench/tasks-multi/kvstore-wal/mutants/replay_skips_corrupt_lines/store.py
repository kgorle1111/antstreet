# Same as the reference; the bug is in log.py: replay silently skips terminated lines that are not
# valid records instead of raising.
def _check_key(key):
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty str")


class KVStore:
    def __init__(self, log):
        self._log = log
        self._data = {}
        for op, key, value in log.replay():
            if op == "set":
                self._data[key] = value
            else:
                self._data.pop(key, None)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        _check_key(key)
        if not isinstance(value, str):
            raise ValueError("value must be a str")
        self._log.append("set", key, value)
        self._data[key] = value

    def delete(self, key):
        _check_key(key)
        if key not in self._data:
            return False
        self._log.append("delete", key)
        del self._data[key]
        return True

    def keys(self):
        return sorted(self._data)

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def compact(self):
        self._log.rewrite([("set", k, self._data[k]) for k in sorted(self._data)])
