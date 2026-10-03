import pytest
from ringbuffer import BufferFull, RingBuffer


def test_popleft_returns_items_oldest_first():
    buf = RingBuffer(3)
    buf.extend([1, 2, 3])
    assert buf.popleft() == 1
    assert len(buf) == 2
    assert list(buf) == [2, 3]
    assert buf.popleft() == 2
    assert buf.popleft() == 3
    assert len(buf) == 0


def test_popleft_on_empty_raises_index_error():
    buf = RingBuffer(2)
    with pytest.raises(IndexError):
        buf.popleft()
    buf.append(1)
    buf.popleft()
    with pytest.raises(IndexError):
        buf.popleft()


def test_popleft_after_overwriting_returns_the_oldest_survivor():
    buf = RingBuffer(3)
    buf.extend(range(8))
    assert buf.popleft() == 5
    assert list(buf) == [6, 7]


def test_append_after_popleft_goes_to_the_newest_end():
    buf = RingBuffer(3)
    buf.extend([1, 2, 3])
    buf.popleft()
    buf.append(4)
    assert list(buf) == [2, 3, 4]
    buf.append(5)
    assert list(buf) == [3, 4, 5]


def test_clear_empties_the_buffer_and_keeps_capacity():
    buf = RingBuffer(3)
    buf.extend(range(5))
    buf.clear()
    assert len(buf) == 0
    assert list(buf) == []
    assert buf.capacity == 3
    assert buf.full is False
    with pytest.raises(IndexError):
        buf.popleft()
    with pytest.raises(IndexError):
        buf[0]


def test_buffer_behaves_like_new_after_clear():
    buf = RingBuffer(3)
    buf.extend(range(5))
    buf.clear()
    buf.extend([10, 20, 30, 40])
    assert list(buf) == [20, 30, 40]
    assert buf[0] == 20 and buf[-1] == 40


def test_clear_keeps_the_overwrite_policy():
    buf = RingBuffer(2, overwrite=False)
    buf.extend([1, 2])
    buf.clear()
    buf.extend([3, 4])
    with pytest.raises(BufferFull):
        buf.append(5)
    assert list(buf) == [3, 4]
