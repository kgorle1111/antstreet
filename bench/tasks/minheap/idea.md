Create a Python module `minheap.py` (standard library only) with one class:

    MinHeap(key: Callable[[Any], Any] | None = None)

    push(item) -> None
    pop() -> item
    peek() -> item
    replace(item) -> item
    items() -> list
    len(heap) -> int
    bool(heap) -> bool

It is a priority queue that always hands back the item with the smallest priority.

1. An item's priority is `key(item)`, or the item itself when `key` is `None`. Priorities are
   compared with `<` only. The items themselves need not be comparable: they may be dicts, and two
   items are never compared with each other, only their priorities.
2. `key` is called exactly once for each item that `push` or `replace` inserts, at the moment it is
   inserted. It is never called for any other reason: `pop`, `peek`, `items`, `len` and `bool`
   do not call it.
3. `pop()` removes and returns the item with the smallest priority. `peek()` returns that item
   without removing it. On an empty heap both raise `IndexError`.
4. Ties are first in, first out: among items whose priorities are equal (neither is `<` the other),
   the one that was inserted earliest comes out first. The same object pushed twice is two separate
   entries.
5. `replace(item)` first removes the smallest item and only then inserts `item`, and it returns the
   item it removed. So even when `item` has a smaller priority than everything in the heap, the
   old smallest item is the one returned and `item` stays inside. For ties, the new item counts as
   inserted after everything already in the heap. On an empty heap `replace` raises `IndexError`
   and the heap stays empty.
6. `items()` returns a new list of all the items in the order that repeated `pop()` calls would
   return them. It does not change the heap, and changing the returned list does not either.
7. `len(heap)` is the number of items. `bool(heap)` is `False` exactly when the heap is empty.
