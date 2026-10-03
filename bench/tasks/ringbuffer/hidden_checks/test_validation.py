import pytest
from ringbuffer import RingBuffer


@pytest.mark.parametrize("capacity", [0, -1, -100])
def test_capacity_below_one_raises_value_error(capacity):
    with pytest.raises(ValueError):
        RingBuffer(capacity)
    with pytest.raises(ValueError):
        RingBuffer(capacity, overwrite=False)


@pytest.mark.parametrize("capacity", [2.5, 3.0, "3", None, [3]])
def test_capacity_that_is_not_an_int_raises_type_error(capacity):
    with pytest.raises(TypeError):
        RingBuffer(capacity)


def test_valid_capacities_are_accepted():
    assert RingBuffer(1).capacity == 1
    assert RingBuffer(2).capacity == 2
    assert RingBuffer(10_000).capacity == 10_000


def test_capacity_does_not_change_as_items_come_and_go():
    buf = RingBuffer(4)
    buf.extend(range(20))
    buf.popleft()
    assert buf.capacity == 4
    buf.clear()
    assert buf.capacity == 4


def test_full_tracks_length_against_capacity():
    buf = RingBuffer(3)
    seen = []
    for n in range(5):
        buf.append(n)
        seen.append(buf.full)
    assert seen == [False, False, True, True, True]
    buf.popleft()
    assert buf.full is False
    buf.append(9)
    assert buf.full is True
