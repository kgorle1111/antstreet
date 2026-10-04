import pytest
from netstring import Decoder


def broken(how):
    d = Decoder()
    with pytest.raises(ValueError):
        d.feed(how)
    return d


@pytest.mark.parametrize("how", [b"x", b"05:", b"3:abcd", b"1234567890", b"1000001:"])
def test_every_later_feed_raises_whatever_the_data(how):
    d = broken(how)
    for later in (b"5:hello,", b"", b"0:,", b"x", bytearray(b"1:a,")):
        with pytest.raises(ValueError):
            d.feed(later)


@pytest.mark.parametrize("how", [b"x", b"05:", b"3:abcd", b"1234567890", b"1000001:"])
def test_close_raises_on_a_broken_decoder(how):
    d = broken(how)
    with pytest.raises(ValueError):
        d.close()
    with pytest.raises(ValueError):
        d.close()


def test_a_broken_decoder_stays_broken_after_a_failed_feed_in_the_middle_of_a_stream():
    d = Decoder()
    assert d.feed(b"3:abc,") == [b"abc"]
    with pytest.raises(ValueError):
        d.feed(b"1:x;")
    with pytest.raises(ValueError):
        d.feed(b"1:y,")


def test_a_new_decoder_is_not_affected_by_another_one_breaking():
    broken(b"x")
    assert Decoder().feed(b"1:a,") == [b"a"]


def test_a_decoder_that_has_not_failed_is_not_broken_by_close_errors():
    d = Decoder()
    d.feed(b"5:he")
    with pytest.raises(ValueError):
        d.close()
    assert d.feed(b"llo,") == [b"hello"]
    assert d.close() is None
