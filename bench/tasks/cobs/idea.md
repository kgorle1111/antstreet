Create a Python module `cobs.py` (standard library only) that implements COBS, Consistent Overhead Byte Stuffing: an encoding of arbitrary bytes that never contains the byte `0x00`, so a zero byte can mark the end of a packet on a serial line. It provides two functions:

    encode(data: bytes) -> bytes
    decode(data: bytes) -> bytes

In this text, bytes are written as Python bytes literals.

The format. The encoded form is a sequence of blocks. A block is a code byte `c` from `0x01` to `0xFF`, followed by `c - 1` data bytes, none of which is `0x00`. Decoding writes the data bytes of every block, and after the block's data it also writes one `0x00` byte, except when the block's code is `0xFF` or when it is the last block.

Encoding. The data is written from left to right as blocks. Each block takes the next bytes that are not `0x00`, at most 254 of them, and has the code byte `len + 1` in front of them. After a block:

- If it took 254 bytes (code `0xFF`), nothing is consumed besides those bytes, and no zero is implied. If the data is now used up, the encoding ends here; otherwise the next block starts at the next byte.
- Otherwise the block stopped before a `0x00` byte or at the end of the data. If the data is used up, the encoding ends here. If it stopped before a `0x00`, that zero is consumed by the block (it is the zero the decoder will write after it) and the next block starts after it. If that zero was the very last byte of the data, the next block is empty, the single byte `0x01`, and the encoding ends after it.

Examples: `b''` encodes to `b'\x01'`; `b'\x00'` to `b'\x01\x01'`; `b'\x00\x00'` to `b'\x01\x01\x01'`; `b'\x00\x11\x00'` to `b'\x01\x02\x11\x01'`; `b'\x11\x22\x00\x33'` to `b'\x03\x11\x22\x02\x33'`; `b'\x11\x22\x33\x44'` to `b'\x05\x11\x22\x33\x44'`; `b'\x11\x00\x00\x00'` to `b'\x02\x11\x01\x01\x01'`. For 254 bytes `01 02 ... FE` (all non-zero) the encoding is `b'\xff'` followed by those 254 bytes, with nothing after them. For the 255 bytes `01 02 ... FF` it is `b'\xff'`, the bytes `01 ... FE`, then `b'\x02\xff'`. For the 254 bytes `02 03 ... FF` followed by one `0x00` it is `b'\xff'`, the 254 bytes, then `b'\x01\x01'`.

1. `encode(data)` follows the rules above for `bytes` or `bytearray`; any other type raises `TypeError`. The result is `bytes`, it never contains `0x00`, and it is never longer than `len(data) + len(data) // 254 + 1`.
2. `decode(data)` reads blocks from the start and returns the data of every block, with a `0x00` after each block whose code is below `0xFF`, except after the last block. It accepts any sequence of valid blocks, not only what `encode` writes: `b'\x01\x01'` is `b'\x00'`, `b'\x03\x11\x22'` is `b'\x11\x22'`, and `b'\xff'` followed by 254 non-zero bytes and then `b'\x01'` is those 254 bytes. The result is `bytes`. `bytes` or `bytearray` is accepted; any other type raises `TypeError`.
3. `decode` raises `ValueError` for empty input, for input that contains a `0x00` byte anywhere (the end-of-packet marker is not part of the data), and for a last block that is cut short: a code byte that promises more data bytes than the input still holds (`b'\x05\x11\x22'`, `b'\x02'`).
4. For every `bytes` value `d`, `decode(encode(d))` equals `d`.
