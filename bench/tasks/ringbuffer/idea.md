Create a Python module `ringbuffer.py` (standard library only) with an exception class and a class:

    class BufferFull(Exception): ...

    RingBuffer(capacity: int, overwrite: bool = True)

    append(item) -> None
    extend(items: Iterable) -> None
    popleft() -> item
    clear() -> None
    buf[i] -> item
    iter(buf), len(buf)
    buf.full -> bool
    buf.capacity -> int

It is a queue that holds at most `capacity` items and never grows. Items are kept from the oldest
to the newest.

1. `capacity` must be an `int` that is at least 1: an int below 1 raises `ValueError` and a value
   that is not an int (a float such as `2.5`, a string, `None`) raises `TypeError`. `buf.capacity`
   returns it.
2. `len(buf)` is the number of items held, never more than `capacity`. Iterating a buffer yields
   its items from the oldest to the newest, and so does `list(buf)`. An item is any object,
   including `None`.
3. `append(item)` adds `item` as the newest item. When the buffer is already full, what happens
   depends on `overwrite`. With `overwrite=True` the oldest item is dropped and `item` is added as
   the newest, so the buffer stays full. With `overwrite=False` `append` raises `BufferFull` and
   the buffer is left exactly as it was.
4. `extend(items)` appends each item in order, exactly as repeated `append` calls would. With
   `overwrite=False`, if the buffer fills up part way, the items before the one that did not fit
   stay appended and `BufferFull` is raised for the first item that did not fit.
5. `popleft()` removes and returns the oldest item, and raises `IndexError` when the buffer is
   empty. Afterwards there is room again, even with `overwrite=False`.
6. `buf[i]` returns an item by position: `buf[0]` is the oldest and `buf[len(buf) - 1]` the newest.
   A negative index counts from the newest: `buf[-1]` is the newest item, `buf[-len(buf)]` the
   oldest. An index outside `-len(buf)` to `len(buf) - 1` raises `IndexError`, including any index
   on an empty buffer.
7. `buf.full` is `True` exactly when `len(buf) == capacity`.
8. `clear()` removes every item and keeps the capacity and the overwrite policy. The buffer then
   behaves like a new one.
9. All of this holds however many times the buffer has wrapped around: a buffer of capacity 7 that
   has had 1,000 items appended holds the last 7 of them, oldest first.
