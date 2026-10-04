# decode_signed never sign-extends, so negative numbers come back as large positive ones.
"""LEB128 codec. Encoders write the shortest form; decoders bound the length by max_bits."""


def _int(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}")


def _bits(max_bits: object) -> int:
    _int(max_bits, "max_bits")
    assert isinstance(max_bits, int)
    if max_bits < 1:
        raise ValueError("max_bits must be at least 1")
    return max_bits


def encode_unsigned(value: int, max_bits: int = 64) -> bytes:
    _int(value, "value")
    bits = _bits(max_bits)
    if not 0 <= value < 1 << bits:
        raise OverflowError(f"{value} does not fit in {bits} unsigned bits")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if not value:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def encode_signed(value: int, max_bits: int = 64) -> bytes:
    _int(value, "value")
    bits = _bits(max_bits)
    if not -(1 << (bits - 1)) <= value < 1 << (bits - 1):
        raise OverflowError(f"{value} does not fit in {bits} signed bits")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7  # arithmetic shift: keeps the sign
        if (value == 0 and not byte & 0x40) or (value == -1 and byte & 0x40):
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def _read(data: bytes, offset: int, max_bits: int) -> tuple[int, int, int]:
    """The raw unsigned payload, how many bytes it took, and the last byte."""
    if not isinstance(data, bytes | bytearray):
        raise TypeError(f"data must be bytes, got {type(data).__name__}")
    _int(offset, "offset")
    bits = _bits(max_bits)
    if not 0 <= offset <= len(data):
        raise ValueError(f"offset {offset} is outside the data")
    limit = -(-bits // 7)
    raw = 0
    for n in range(limit):
        if offset + n >= len(data):
            raise ValueError("the data ends inside a number")
        byte = data[offset + n]
        raw |= (byte & 0x7F) << (7 * n)
        if not byte & 0x80:
            return raw, n + 1, byte
    raise OverflowError(f"more than {limit} bytes for a {bits}-bit number")


def decode_unsigned(data: bytes, offset: int = 0, max_bits: int = 64) -> tuple[int, int]:
    raw, length, _ = _read(data, offset, max_bits)
    if raw >> max_bits:
        raise OverflowError(f"{raw} does not fit in {max_bits} unsigned bits")
    return raw, offset + length


def decode_signed(data: bytes, offset: int = 0, max_bits: int = 64) -> tuple[int, int]:
    raw, length, last = _read(data, offset, max_bits)
    value = raw
    if not -(1 << (max_bits - 1)) <= value < 1 << (max_bits - 1):
        raise OverflowError(f"{value} does not fit in {max_bits} signed bits")
    return value, offset + length
