from minheap import MinHeap


def drain(heap):
    out = []
    while heap:
        out.append(heap.pop())
    return out


def test_pops_in_ascending_order():
    heap = MinHeap()
    for n in [5, 1, 9, 3, 7, 2, 8]:
        heap.push(n)
    assert drain(heap) == [1, 2, 3, 5, 7, 8, 9]


def test_peek_does_not_remove():
    heap = MinHeap()
    heap.push(4)
    heap.push(2)
    assert heap.peek() == 2
    assert heap.peek() == 2
    assert len(heap) == 2
    assert heap.pop() == 2
    assert heap.peek() == 4


def test_key_function_orders_by_priority():
    heap = MinHeap(key=len)
    for word in ["pear", "fig", "banana", "kiwi!", "yo"]:
        heap.push(word)
    assert drain(heap) == ["yo", "fig", "pear", "kiwi!", "banana"]


def test_negating_key_makes_a_max_heap():
    heap = MinHeap(key=lambda n: -n)
    for n in [3, 10, -4, 7]:
        heap.push(n)
    assert drain(heap) == [10, 7, 3, -4]


def test_tuples_and_mixed_int_float_priorities():
    heap = MinHeap()
    for item in [(2, "b"), (1, "z"), (1, "a"), (0, "q")]:
        heap.push(item)
    assert drain(heap) == [(0, "q"), (1, "a"), (1, "z"), (2, "b")]
    heap = MinHeap()
    for n in [2, 1.5, 1, 2.5]:
        heap.push(n)
    assert drain(heap) == [1, 1.5, 2, 2.5]


def test_push_after_pop_keeps_working():
    heap = MinHeap()
    heap.push(5)
    heap.push(3)
    assert heap.pop() == 3
    heap.push(1)
    heap.push(4)
    assert drain(heap) == [1, 4, 5]
    heap.push(9)
    assert heap.pop() == 9
