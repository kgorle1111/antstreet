from minheap import MinHeap


def test_items_is_the_pop_order_without_changing_the_heap():
    heap = MinHeap(key=lambda t: t[0])
    for item in [(3, "a"), (1, "b"), (2, "c"), (1, "d")]:
        heap.push(item)
    before = heap.items()
    assert before == [(1, "b"), (1, "d"), (2, "c"), (3, "a")]
    assert heap.items() == before
    assert len(heap) == 4
    assert [heap.pop() for _ in range(4)] == before


def test_items_returns_a_new_list_each_time():
    heap = MinHeap()
    heap.push(2)
    heap.push(1)
    snapshot = heap.items()
    snapshot.clear()
    snapshot.append(99)
    assert heap.items() == [1, 2]
    assert heap.items() is not heap.items()
    assert len(heap) == 2


def test_items_after_pushes_and_pops():
    heap = MinHeap()
    for n in [4, 2, 6]:
        heap.push(n)
    heap.pop()
    heap.push(1)
    assert heap.items() == [1, 4, 6]
