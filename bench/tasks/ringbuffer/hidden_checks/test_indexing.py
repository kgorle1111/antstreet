import pytest
from ringbuffer import RingBuffer


def test_positive_and_negative_indexes_on_a_partly_filled_buffer():
    buf = RingBuffer(5)
    buf.extend(["a", "b", "c"])
    assert buf[0] == "a"
    assert buf[2] == "c"
    assert buf[-1] == "c"
    assert buf[-3] == "a"


def test_indexes_after_wrapping():
    buf = RingBuffer(4)
    buf.extend(range(10))
    assert [buf[i] for i in range(4)] == [6, 7, 8, 9]
    assert [buf[-i] for i in range(1, 5)] == [9, 8, 7, 6]


def test_out_of_range_indexes_raise_index_error():
    buf = RingBuffer(4)
    buf.extend([1, 2, 3])
    for bad in (3, 4, 100, -4, -5, -100):
        with pytest.raises(IndexError):
            buf[bad]


def test_index_equal_to_len_is_out_of_range_even_when_a_slot_is_free():
    buf = RingBuffer(5)
    buf.extend([1, 2])
    with pytest.raises(IndexError):
        buf[2]
    with pytest.raises(IndexError):
        buf[-3]


def test_any_index_on_an_empty_buffer_raises():
    buf = RingBuffer(3)
    for bad in (0, 1, -1):
        with pytest.raises(IndexError):
            buf[bad]


def test_negative_index_is_correct_on_a_partly_filled_wrapped_buffer():
    buf = RingBuffer(5)
    buf.extend(range(8))
    buf.popleft()
    buf.popleft()
    assert list(buf) == [5, 6, 7]
    assert buf[-1] == 7
    assert buf[-3] == 5
    assert buf[0] == 5
    with pytest.raises(IndexError):
        buf[3]


def test_indexes_track_every_state_of_a_busy_buffer():
    buf = RingBuffer(4)
    items = []
    for n in range(30):
        buf.append(n)
        items = (items + [n])[-4:]
        if n % 3 == 0:
            buf.popleft()
            items = items[1:]
        for i, value in enumerate(items):
            assert buf[i] == value
            assert buf[i - len(items)] == value
