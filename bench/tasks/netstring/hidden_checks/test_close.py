import pytest
from netstring import Decoder


def test_a_new_decoder_closes_cleanly():
    assert Decoder().close() is None


def test_closing_between_frames_is_clean():
    d = Decoder()
    d.feed(b"5:hello,")
    assert d.close() is None
    d.feed(b"0:,3:abc,")
    assert d.close() is None


def test_closing_after_empty_pieces_only_is_clean():
    d = Decoder()
    d.feed(b"")
    assert d.close() is None


@pytest.mark.parametrize(
    "piece",
    [
        b"1",  # after some length digits
        b"12",
        b"0",
        b"3:",  # right after the colon
        b"0:",
        b"3:a",  # inside the payload
        b"3:ab",
        b"3:abc",  # just before the closing comma
        b"0:",
        b"5:hello,2",  # a second frame has begun
        b"5:hello,2:a",
    ],
)
def test_closing_inside_a_frame_raises_value_error(piece):
    d = Decoder()
    d.feed(piece)
    with pytest.raises(ValueError):
        d.close()


def test_close_does_not_change_the_state():
    d = Decoder()
    d.feed(b"3:ab")
    for _ in range(3):
        with pytest.raises(ValueError):
            d.close()
    assert d.feed(b"c,") == [b"abc"]
    assert d.close() is None
    assert d.close() is None


def test_close_returns_none_not_a_list():
    d = Decoder()
    d.feed(b"1:a,")
    assert d.close() is None


def test_close_after_a_frame_split_across_pieces():
    d = Decoder()
    for piece in (b"1", b"0", b":", b"0123", b"456789", b","):
        d.feed(piece)
    assert d.close() is None
