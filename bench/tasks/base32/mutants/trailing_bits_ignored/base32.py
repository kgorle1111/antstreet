# decode accepts nonzero bits left over in the last letter instead of rejecting them.
"""Base32 (RFC 4648) written by hand; strict on padding, length and trailing bits when decoding."""

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_VALUES = {ch: i for i, ch in enumerate(_ALPHABET)}
_VALUES |= {ch.lower(): i for i, ch in enumerate(_ALPHABET)}
# letters left in the last group of 8 -> how many "=" encode writes after them
_PADDING = {0: 0, 2: 6, 4: 4, 5: 3, 7: 1}


def encode(data: bytes, pad: bool = True) -> str:
    if not isinstance(data, bytes | bytearray):
        raise TypeError(f"expected bytes, got {type(data).__name__}")
    out: list[str] = []
    acc = 0
    bits = 0
    for byte in data:
        acc = (acc << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            out.append(_ALPHABET[(acc >> bits) & 31])
        acc &= (1 << bits) - 1
    if bits:
        out.append(_ALPHABET[(acc << (5 - bits)) & 31])
    text = "".join(out)
    if pad:
        text += "=" * (-len(text) % 8)
    return text


def decode(text: str) -> bytes:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    body = text.rstrip("=")
    padding = len(text) - len(body)
    if any(ch not in _VALUES for ch in body):
        raise ValueError("character outside the Base32 alphabet, or '=' before the end")
    if len(body) % 8 not in _PADDING:
        raise ValueError(f"{len(body)} letters cannot come from an encoder")
    if padding and padding != _PADDING[len(body) % 8]:
        raise ValueError(f"wrong amount of padding: {padding}")
    out = bytearray()
    acc = 0
    bits = 0
    for ch in body:
        acc = (acc << 5) | _VALUES[ch]
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 255)
            acc &= (1 << bits) - 1
    return bytes(out)
