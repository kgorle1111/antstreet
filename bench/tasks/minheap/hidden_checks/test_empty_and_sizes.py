import pytest
from minheap import MinHeap


def test_new_heap_is_empty():
    heap = MinHeap()
    assert len(heap) == 0
    assert not heap
    assert heap.items() == []


def test_pop_and_peek_on_empty_raise_index_error():
    heap = MinHeap()
    with pytest.raises(IndexError):
        heap.pop()
    with pytest.raises(IndexError):
        heap.peek()


def test_draining_returns_to_empty_behaviour():
    heap = MinHeap()
    heap.push(1)
    heap.push(2)
    heap.pop()
    heap.pop()
    assert len(heap) == 0
    assert not heap
    with pytest.raises(IndexError):
        heap.pop()
    heap.push(7)
    assert heap.peek() == 7


def test_len_and_bool_track_pushes_and_pops():
    heap = MinHeap()
    for n in range(5):
        heap.push(n)
        assert len(heap) == n + 1
        assert heap
    for n in range(5):
        heap.pop()
        assert len(heap) == 4 - n
    assert not heap


def test_error_leaves_the_heap_usable_and_unchanged():
    heap = MinHeap()
    with pytest.raises(IndexError):
        heap.pop()
    heap.push(3)
    assert heap.items() == [3]
