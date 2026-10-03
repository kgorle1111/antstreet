Create a Python module `netstring.py` (standard library only) that frames byte messages as netstrings and reassembles them from a stream that arrives in arbitrary pieces. It provides one function and one class:

    encode(payload: bytes) -> bytes
    class Decoder:
        def __init__(self, max_length: int = 1_000_000) -> None
        def feed(self, data: bytes) -> list[bytes]
        def close(self) -> None

A netstring is the payload's length in decimal ASCII digits, a colon, the payload bytes, and a comma. In this text, examples of bytes are written as Python bytes literals.

1. `encode(b'hello')` is `b'5:hello,'` and `encode(b'')` is `b'0:,'`. The payload may hold any bytes, including `:`, `,`, digits and newlines; the length counts bytes, so `encode(b'\xc3\xa9')` is `b'2:\xc3\xa9,'`. A `bytearray` is accepted too. Any other type, including `str`, raises `TypeError`.

The decoder:

2. `feed(data)` takes the next piece of the stream, of any size, even empty, and returns a list of the payloads (as `bytes`) of every netstring that this piece completed, in stream order. A netstring is complete only when its closing comma has arrived. A piece may hold several netstrings, part of one, or end or start anywhere inside one, including inside the length digits; the decoder keeps what it has not finished between calls. Feeding `b'5:he'` returns `[]` and then feeding `b'llo,3:abc,'` returns `[b'hello', b'abc']`. A payload is returned once only. `feed` accepts `bytes` or `bytearray`; any other type raises `TypeError`, and that leaves the decoder exactly as it was.
3. The length is 1 to 9 ASCII digits with no leading zeros (`0` itself is fine, `00:` and `05:` are not), followed by `:`. After the payload comes exactly one `,`; any other byte there is an error. All errors raise `ValueError` as soon as the offending byte has been fed, without waiting for more data: a first byte that is not a digit (`b'x'`, `b':'`, `b'-'`, a space), a digit after a leading `0`, a tenth digit, a byte after the digits that is not a digit or `:`, and a byte that is not `,` after the payload. `b'5:hello;'` raises, and so does `b'3:abcd'`.
4. `max_length` is the largest payload length accepted. As soon as the colon after a length larger than `max_length` has been fed, `feed` raises `ValueError`, before any payload arrives. A length equal to `max_length` is accepted, and `max_length=0` accepts only `b'0:,'` frames. With the default, `b'1000000:'` is accepted and `b'1000001:'` raises.
5. After `feed` has raised `ValueError`, the decoder is broken: every later `feed` and `close` call raises `ValueError`, whatever the data.
6. `close()` says the stream has ended. It returns `None` when the decoder is between netstrings: nothing was fed, or the last netstring was completed by its comma. It raises `ValueError` when the stream ended inside one, whether that is after some length digits, after the colon, inside the payload, or just before the closing comma (`b'12'`, `b'3:'`, `b'3:ab'`, `b'3:abc'`). Calling `close()` does not change the decoder's state.
7. For any list of payloads, feeding `b''.join(map(encode, payloads))` to a new `Decoder` in any partition into pieces returns exactly those payloads, in order, over the calls taken together.
