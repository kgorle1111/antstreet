Create a Python module `base32.py` (standard library only) that encodes and decodes Base32 (the RFC 4648 alphabet) by hand. Do not import `base64`; the module is judged on behaviour only, but the point is to write the codec yourself. It provides two functions:

    encode(data: bytes, pad: bool = True) -> str
    decode(text: str) -> bytes

The alphabet is the 26 uppercase letters `A`-`Z` for the values 0-25, then the digits `2`-`7` for the values 26-31. Padding is the character `=`.

Encoding:

1. The input bytes are read as one stream of bits, most significant bit first, and cut into groups of 5 bits, each written as one alphabet character. A last group that has fewer than 5 bits is filled on the right with zero bits. `b'f'` is `MY`, `b'fo'` is `MZXQ`, `b'foo'` is `MZXW6`, `b'foob'` is `MZXW6YQ`, `b'fooba'` is `MZXW6YTB`, `b'foobar'` is `MZXW6YTBOI`, and `b''` is `""`. The output is always upper case.
2. With `pad=True` (the default) the output is then filled on the right with `=` until its length is a multiple of 8: `b'f'` is `MY======`, `b'fo'` is `MZXQ====`, `b'foo'` is `MZXW6===`, `b'foob'` is `MZXW6YQ=`, and `b'fooba'` and `b'foobar'` stay `MZXW6YTB` and `MZXW6YTBOI======`. With `pad=False` no `=` is written.
3. `data` may be `bytes` or `bytearray`. Any other type, including a `str`, raises `TypeError`.

Decoding:

4. Letters may be upper or lower case; both spellings of a letter have the same value. The digits `0`, `1`, `8` and `9`, whitespace of any kind, and every other character that is not in the alphabet or `=` raise `ValueError`.
5. Padding is optional. `MY======` and `MY` both decode to `b'f'`. When `=` is present it may only be at the end of the text, and there must be exactly as many as `encode` writes with `pad=True` for that data (6 after 2 letters, 4 after 4, 3 after 5, 1 after 7, and none after a multiple of 8 letters). Anything else raises `ValueError`: `MY=`, `MY=======`, `MZXW6YTB=` (a full group followed by padding), `=`, `M=Y=====` and `========`.
6. The letters, not counting padding, must leave a length that `encode` could have produced. Counted modulo 8 that is 0, 2, 4, 5 or 7 letters; 1, 3 or 6 raises `ValueError` (`M`, `MZX`, `MZXW6Y`).
7. The bits left over in the last letter must all be zero, as `encode` writes them. `MZ` would need its last 2 bits to be 0 and they are not, so it raises `ValueError`; `MY` is fine.
8. The empty string decodes to `b''`. The result is always `bytes`. A `text` that is not a `str` raises `TypeError`.
9. For every `bytes` value `d`, `decode(encode(d))` and `decode(encode(d, pad=False))` both equal `d`.
