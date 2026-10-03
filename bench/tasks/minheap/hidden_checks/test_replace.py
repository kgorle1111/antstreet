import pytest
from minheap import MinHeap


def test_replace_returns_the_old_smallest_and_inserts_the_new_item():
    heap = MinHeap()
    for n in [3, 5, 8]:
        heap.push(n)
    assert heap.replace(6) == 3
    assert heap.items() == [5, 6, 8]
    assert len(heap) == 3


def test_replace_with_a_smaller_item_still_returns_the_old_smallest():
    heap = MinHeap()
    for n in [3, 5, 8]:
        heap.push(n)
    assert heap.replace(1) == 3
    assert heap.peek() == 1
    assert heap.items() == [1, 5, 8]


def test_replace_on_a_single_item_heap():
    heap = MinHeap()
    heap.push(10)
    assert heap.replace(2) == 10
    assert heap.items() == [2]


def test_replaced_item_counts_as_inserted_last_for_ties():
    heap = MinHeap(key=lambda t: t[0])
    heap.push((1, "a"))
    heap.push((1, "b"))
    heap.push((2, "c"))
    assert heap.replace((1, "new")) == (1, "a")
    assert heap.items() == [(1, "b"), (1, "new"), (2, "c")]


def test_replace_on_an_empty_heap_raises_and_inserts_nothing():
    heap = MinHeap()
    with pytest.raises(IndexError):
        heap.replace(1)
    assert len(heap) == 0
    assert not heap
    assert heap.items() == []
