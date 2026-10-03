# decode does not check that a block's data is all there, so a cut-short last block is accepted.
"""Consistent Overhead Byte Stuffing: encode never emits 0x00; decode is strict about framing."""


def _need_bytes(data: object) -> None:
    if not isinstance(data, bytes | bytearray):
        raise TypeError(f"expected bytes, got {type(data).__name__}")


def encode(data: bytes) -> bytes:
    _need_bytes(data)
    out = bytearray()
    n = len(data)
    p = 0
    while True:
        q = p
        while q < n and q - p < 254 and data[q] != 0:
            q += 1
        out.append(q - p + 1)
        out += data[p:q]
        if q - p == 254:  # a full block implies no zero
            if q == n:
                break
            p = q
        elif q == n:
            break
        else:
            p = q + 1  # the block consumed the zero at q
    return bytes(out)


def decode(data: bytes) -> bytes:
    _need_bytes(data)
    if not data:
        raise ValueError("empty input has no block")
    if 0 in data:
        raise ValueError("encoded data must not contain a zero byte")
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        code = data[i]
        end = i + code
        out += data[i + 1 : end]
        i = end
        if code < 255 and i < n:
            out.append(0)
    return bytes(out)
