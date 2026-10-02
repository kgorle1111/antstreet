from minheap import MinHeap


def counting_key():
    calls = []

    def key(item):
        calls.append(item)
        return item

    return key, calls


def test_key_is_called_once_per_pushed_item_and_only_then():
    key, calls = counting_key()
    heap = MinHeap(key=key)
    for n in [5, 3, 9, 1, 7, 2]:
        heap.push(n)
    assert sorted(calls) == [1, 2, 3, 5, 7, 9]


def test_pop_peek_items_len_and_bool_never_call_key():
    key, calls = counting_key()
    heap = MinHeap(key=key)
    for n in [5, 3, 9, 1, 7, 2]:
        heap.push(n)
    calls.clear()
    heap.peek()
    heap.items()
    len(heap)
    bool(heap)
    while heap:
        heap.pop()
    assert calls == []


def test_replace_calls_key_once_for_the_new_item_only():
    key, calls = counting_key()
    heap = MinHeap(key=key)
    for n in [5, 3, 9]:
        heap.push(n)
    calls.clear()
    assert heap.replace(4) == 3
    assert calls == [4]


def test_priority_is_read_at_insertion_time_not_later():
    heap = MinHeap(key=lambda d: d["p"])
    a = {"p": 5}
    b = {"p": 3}
    heap.push(a)
    heap.push(b)
    a["p"] = 0
    b["p"] = 100
    assert heap.pop() is b
    assert heap.pop() is a
