import pytest
from ringbuffer import BufferFull, RingBuffer


def test_append_to_a_full_buffer_raises_buffer_full():
    buf = RingBuffer(2, overwrite=False)
    buf.append(1)
    buf.append(2)
    with pytest.raises(BufferFull):
        buf.append(3)


def test_buffer_is_exactly_as_it_was_after_the_failed_append():
    buf = RingBuffer(3, overwrite=False)
    buf.extend([1, 2, 3])
    for _ in range(2):
        with pytest.raises(BufferFull):
            buf.append(99)
    assert list(buf) == [1, 2, 3]
    assert len(buf) == 3
    assert buf[0] == 1 and buf[-1] == 3
    assert buf.full is True


def test_buffer_full_is_an_exception_class_defined_in_the_module():
    assert issubclass(BufferFull, Exception)


def test_popleft_makes_room_again():
    buf = RingBuffer(3, overwrite=False)
    buf.extend([1, 2, 3])
    assert buf.popleft() == 1
    assert buf.full is False
    buf.append(4)
    assert list(buf) == [2, 3, 4]
    with pytest.raises(BufferFull):
        buf.append(5)
    assert list(buf) == [2, 3, 4]


def test_extend_that_does_not_fit_keeps_the_items_that_did():
    buf = RingBuffer(4, overwrite=False)
    buf.append("x")
    with pytest.raises(BufferFull):
        buf.extend(["a", "b", "c", "d", "e"])
    assert list(buf) == ["x", "a", "b", "c"]
    assert len(buf) == 4


def test_extend_that_exactly_fits_does_not_raise():
    buf = RingBuffer(3, overwrite=False)
    buf.extend([1, 2, 3])
    assert list(buf) == [1, 2, 3]


def test_not_full_buffer_with_overwrite_false_behaves_normally():
    buf = RingBuffer(5, overwrite=False)
    buf.extend([1, 2, 3])
    buf.popleft()
    buf.append(4)
    assert list(buf) == [2, 3, 4]


def test_order_stays_right_after_pops_and_refills():
    buf = RingBuffer(3, overwrite=False)
    expected = []
    n = 0
    for _ in range(40):
        while not buf.full:
            buf.append(n)
            expected.append(n)
            n += 1
        buf.popleft()
        expected.pop(0)
        buf.popleft()
        expected.pop(0)
        assert list(buf) == expected
