Create two Python modules, `log.py` and `store.py` (standard library only), that together make a small durable key-value store: an append-only write-ahead log and a store that is rebuilt from it. `store.py` does not need to import `log.py`; the store only calls the methods named below on the log object it is given.

`log.py` provides one class:

    WriteAheadLog(path: str | os.PathLike)
    append(op: str, key: str, value: str | None = None) -> None
    replay() -> list[tuple[str, str, str | None]]
    rewrite(records: list[tuple[str, str, str | None]]) -> None

`store.py` provides one class:

    KVStore(log: WriteAheadLog)
    get(key: str, default=None)
    set(key: str, value: str) -> None
    delete(key: str) -> bool
    keys() -> list[str]
    len(store) -> int
    key in store -> bool
    compact() -> None

The log:

1. `path` is a file. Constructing a `WriteAheadLog` does not touch the file system. The file may not exist yet.
2. A record is a tuple `(op, key, value)`. `op` is `"set"` or `"delete"`. `key` is a non-empty `str`. For `"set"`, `value` is a `str` (the empty string is allowed). For `"delete"`, the value is always stored and returned as `None`, whatever `append` or `rewrite` was given.
3. `append` validates the record and raises `ValueError` for anything invalid: an `op` other than the two above, a `key` that is not a `str` or is empty, a `"set"` whose `value` is not a `str`. An invalid record writes nothing.
4. On disk the log is a text file in UTF-8. Each record is one line: a JSON object with exactly the keys `"op"`, `"key"` and `"value"` (`value` is `null` for deletes), followed by a single `"\n"`. Newlines and other control characters inside keys and values are escaped by JSON, so one record is always exactly one line and the file holds exactly one `"\n"` per record. `append` adds its line to the end of the file (creating the file if needed) and has flushed it before it returns. Earlier lines are never changed by `append`.
5. `replay()` reads the file and returns the records in file order as a list of `(op, key, value)` tuples. A missing file gives `[]`. `replay` never modifies the file.
6. Only lines ended by `"\n"` are records. Any text after the last `"\n"` is a torn write from a crash: `replay` ignores it, even when it would parse as a complete record.
7. A line ended by `"\n"` that is not a valid record makes `replay` raise `ValueError`. Not valid means: not JSON, not an object with exactly those three keys, an invalid `op`, `key` or `value` by rule 2, a delete whose `value` is not `null`, or an empty line. Corruption is never skipped.
8. `rewrite(records)` validates every record by rules 2 and 3 (raising `ValueError` before touching the file if any is invalid) and then replaces the whole file with exactly those records, in order, in the format of rule 4. It writes a temporary file in the same directory and swaps it in with `os.replace`, so a crash never leaves a half-written log. `rewrite([])` leaves an empty file. No other file is left in the directory afterwards.

The store:

9. `KVStore(log)` starts empty and then applies `log.replay()` in order: a `"set"` record sets the key, a `"delete"` record removes it (and does nothing if the key is absent). Any error from `replay` propagates out of the constructor.
10. `set(key, value)` raises `ValueError` if `key` is not a non-empty `str` or `value` is not a `str`. Otherwise it calls `log.append("set", key, value)` first and only if that returns normally updates its own state. If `append` raises, the exception propagates and the store is unchanged. Every `set` appends a record, even when the value is unchanged.
11. `delete(key)` raises `ValueError` if `key` is not a non-empty `str`. If the key is present it calls `log.append("delete", key)` first and, only if that returns normally, removes the key and returns `True`; if `append` raises, the exception propagates and the key is still present. If the key is absent it returns `False` and appends nothing.
12. `get(key, default=None)` returns the stored value, or `default` when the key is absent. A stored empty string is a real value, not a missing one. `key in store` is `True` exactly when the key is present. `len(store)` is the number of present keys. `keys()` returns a new list of the present keys in ascending order. None of these touch the log.
13. `compact()` calls `log.rewrite(records)` with one `("set", key, value)` record for every present key, ordered by key ascending, and nothing else (no records for deleted keys, no history). If `rewrite` raises, the exception propagates and the store is unchanged. A store reopened on the same file afterwards has the same contents.
