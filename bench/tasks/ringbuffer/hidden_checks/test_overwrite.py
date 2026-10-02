from collections import deque

from ringbuffer import RingBuffer


def test_full_buffer_drops_the_oldest_item():
    buf = RingBuffer(3)
    buf.extend([1, 2, 3])
    buf.append(4)
    assert list(buf) == [2, 3, 4]
    assert len(buf) == 3
    assert buf.full is True


def test_overwrite_is_the_default_and_can_be_explicit():
    a = RingBuffer(2)
    b = RingBuffer(2, overwrite=True)
    c = RingBuffer(2, True)
    for buf in (a, b, c):
        buf.extend([1, 2, 3])
        assert list(buf) == [2, 3]


def test_order_survives_wrapping_part_way_round():
    buf = RingBuffer(4)
    buf.extend(range(6))
    assert list(buf) == [2, 3, 4, 5]
    buf.append(6)
    assert list(buf) == [3, 4, 5, 6]
    buf.extend([7, 8, 9])
    assert list(buf) == [6, 7, 8, 9]


def test_a_thousand_appends_into_capacity_seven():
    buf = RingBuffer(7)
    for n in range(1000):
        buf.append(n)
        assert list(buf) == list(range(max(0, n - 6), n + 1))
    assert len(buf) == 7


def test_capacity_one_keeps_only_the_latest():
    buf = RingBuffer(1)
    buf.append("a")
    assert buf.full is True
    buf.append("b")
    buf.append("c")
    assert list(buf) == ["c"]
    assert buf[0] == buf[-1] == "c"
    assert buf.popleft() == "c"
    assert len(buf) == 0


def test_extend_with_more_items_than_capacity_keeps_the_last_ones():
    buf = RingBuffer(3)
    buf.extend(range(10))
    assert list(buf) == [7, 8, 9]


def test_matches_a_bounded_deque():
    model = deque(maxlen=5)
    buf = RingBuffer(5)
    for n in range(57):
        model.append(n * n)
        buf.append(n * n)
        assert list(buf) == list(model)
        assert len(buf) == len(model)
