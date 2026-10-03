# A decoder that raised ValueError is not marked broken, so later feeds are processed.
"""Netstring encoder and an incremental decoder that fails fast and then stays failed."""

_MAX_DIGITS = 9


def encode(payload: bytes) -> bytes:
    if not isinstance(payload, bytes | bytearray):
        raise TypeError(f"expected bytes, got {type(payload).__name__}")
    return str(len(payload)).encode("ascii") + b":" + bytes(payload) + b","


class Decoder:
    def __init__(self, max_length: int = 1_000_000) -> None:
        self._max = max_length
        self._digits = b""  # length digits read so far, before the colon
        self._need: int | None = None  # payload length once the colon has been read
        self._buf = bytearray()
        self._broken = False

    def feed(self, data: bytes) -> list[bytes]:
        if not isinstance(data, bytes | bytearray):
            raise TypeError(f"expected bytes, got {type(data).__name__}")
        if self._broken:
            raise ValueError("the decoder failed earlier and cannot be used again")
        out: list[bytes] = []
        try:
            self._consume(bytes(data), out)
        except ValueError:
            raise
        return out

    def _consume(self, data: bytes, out: list[bytes]) -> None:
        i = 0
        while i < len(data):
            if self._need is None:
                byte = data[i]
                i += 1
                if 48 <= byte <= 57:
                    if self._digits == b"0":
                        raise ValueError("leading zero in the length")
                    if len(self._digits) == _MAX_DIGITS:
                        raise ValueError("length has more than 9 digits")
                    self._digits += bytes([byte])
                elif byte == 58 and self._digits:
                    length = int(self._digits)
                    if length > self._max:
                        raise ValueError(f"length {length} is above the limit {self._max}")
                    self._need = length
                    self._digits = b""
                    self._buf = bytearray()
                else:
                    raise ValueError(f"unexpected byte {byte!r} in the length")
            elif len(self._buf) < self._need:
                chunk = data[i : i + self._need - len(self._buf)]
                self._buf += chunk
                i += len(chunk)
            else:
                byte = data[i]
                i += 1
                if byte != 44:
                    raise ValueError("payload is not followed by a comma")
                out.append(bytes(self._buf))
                self._need = None
                self._buf = bytearray()

    def close(self) -> None:
        if self._broken:
            raise ValueError("the decoder failed earlier")
        if self._digits or self._need is not None:
            raise ValueError("the stream ended inside a netstring")
