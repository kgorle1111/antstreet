Create a Python module `leb128.py` (standard library only) that encodes and decodes integers in LEB128, the variable-length format used by WebAssembly, DWARF and protobuf varints. It provides four functions:

    encode_unsigned(value: int, max_bits: int = 64) -> bytes
    encode_signed(value: int, max_bits: int = 64) -> bytes
    decode_unsigned(data: bytes, offset: int = 0, max_bits: int = 64) -> tuple[int, int]
    decode_signed(data: bytes, offset: int = 0, max_bits: int = 64) -> tuple[int, int]

The format. A number is written as a sequence of bytes, least significant group first. Each byte holds 7 bits of the number in its low bits; its high bit (`0x80`) is set on every byte except the last. In this text, bytes are written as Python bytes literals.

1. Unsigned: the number is cut into 7-bit groups from the least significant end. `0` is `b'\x00'`, `127` is `b'\x7f'`, `128` is `b'\x80\x01'`, `255` is `b'\xff\x01'`, `16384` is `b'\x80\x80\x01'`, and `624485` is `b'\xe5\x8e\x26'`.
2. Signed: the number is written in two's complement, cut into 7-bit groups the same way, and it stops at the first byte after which all the remaining higher bits would be a copy of bit 6 (`0x40`) of that byte, which is the sign bit. `0` is `b'\x00'`, `-1` is `b'\x7f'`, `63` is `b'\x3f'`, `64` is `b'\xc0\x00'` (a single byte `\x40` would read as negative), `-64` is `b'\x40'`, `-65` is `b'\xbf\x7f'`, `-128` is `b'\x80\x7f'`, `127` is `b'\xff\x00'`, and `-123456` is `b'\xc0\xbb\x78'`.
3. The encoders write the shortest form, with no extra bytes.

Encoding errors:

4. `max_bits` is the width of the integer type: an unsigned value must be in `0 <= value < 2**max_bits`, and a signed value in `-2**(max_bits-1) <= value < 2**(max_bits-1)`. A `value` outside that range raises `OverflowError`. A `value` or `max_bits` that is not an `int` (a `bool` is not accepted either) raises `TypeError`. A `max_bits` below 1 raises `ValueError`. This is also the rule for `max_bits` in the decoders.

Decoding:

5. `decode_unsigned(data, offset)` and `decode_signed(data, offset)` read one number that starts at `data[offset]` and return `(value, next_offset)`, where `next_offset` is the index just after its last byte. Bytes after the number are not read: `decode_unsigned(b'\x80\x01\xff', 0)` is `(128, 2)`, and `decode_unsigned(b'\xaa\x05\x07', 1)` is `(5, 2)`. In the signed form, bit 6 of the last byte is the sign: when it is set the value is negative (the missing higher bits are ones). `data` must be `bytes` or `bytearray`, any other type raises `TypeError`; `offset` must be an `int` (not a `bool`), else `TypeError`, and must satisfy `0 <= offset <= len(data)`, else `ValueError`.
6. The decoders accept a number written with extra bytes, as long as it fits the limit of rule 7: `b'\x80\x00'` is the unsigned `0` and `b'\xff\x7f'` is the signed `-1`.
7. A number may not use more than `ceil(max_bits / 7)` bytes (10 for the default of 64 bits, 5 for `max_bits=32`, 1 for `max_bits=7`). If the last byte allowed still has its high bit set, the decoder raises `OverflowError`, whether or not the data holds more bytes after it.
8. If the data ends before the number does, the decoder raises `ValueError`: there is no byte at `offset`, or every byte up to the end of the data has its high bit set and the data ended before the limit of rule 7 was reached.
9. When the number is complete, it must fit the type: unsigned `value < 2**max_bits`, signed `-2**(max_bits-1) <= value < 2**(max_bits-1)`; otherwise `OverflowError`. So `decode_unsigned` of the ten bytes `b'\xff' * 9 + b'\x01'` is `2**64 - 1`, while `b'\xff' * 9 + b'\x02'` raises `OverflowError`; and `decode_signed` of `b'\x80' * 9 + b'\x7f'` is `-2**63`, while `b'\xff' * 9 + b'\x7f'` is `-1` written with extra bytes.
10. For every value in range, decoding what the encoder wrote gives back the value and the length of the encoding.
