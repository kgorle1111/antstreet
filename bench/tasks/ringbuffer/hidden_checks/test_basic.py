from ringbuffer import RingBuffer


def test_new_buffer_is_empty():
    buf = RingBuffer(3)
    assert len(buf) == 0
    assert list(buf) == []
    assert buf.capacity == 3
    assert buf.full is False


def test_append_keeps_oldest_to_newest_order():
    buf = RingBuffer(5)
    for n in [10, 20, 30]:
        buf.append(n)
    assert list(buf) == [10, 20, 30]
    assert len(buf) == 3
    assert buf.full is False


def test_extend_appends_in_order():
    buf = RingBuffer(5)
    buf.extend([1, 2])
    buf.extend(iter([3, 4]))
    buf.extend([])
    assert list(buf) == [1, 2, 3, 4]


def test_filling_to_exactly_capacity():
    buf = RingBuffer(3)
    buf.extend(["a", "b", "c"])
    assert list(buf) == ["a", "b", "c"]
    assert len(buf) == 3
    assert buf.full is True


def test_none_and_falsy_items_are_ordinary_items():
    buf = RingBuffer(4)
    buf.extend([None, 0, "", None])
    assert len(buf) == 4
    assert list(buf) == [None, 0, "", None]
    assert buf.popleft() is None
    assert len(buf) == 3


def test_iteration_can_be_repeated_and_nested():
    buf = RingBuffer(3)
    buf.extend([1, 2, 3])
    assert list(buf) == list(buf) == [1, 2, 3]
    pairs = [(a, b) for a in buf for b in buf]
    assert len(pairs) == 9
