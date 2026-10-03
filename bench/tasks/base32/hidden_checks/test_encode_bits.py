from base32 import encode


def test_the_alphabet_is_a_to_z_then_2_to_7():
    # the 5-bit values 0..31 packed into 20 bytes (160 bits) give 32 characters
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    bits = "".join(f"{i:05b}" for i in range(32))
    raw = bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits), 8))
    assert len(raw) == 20
    assert encode(raw) == alphabet


def test_a_short_last_group_is_filled_with_zero_bits_on_the_right():
    assert encode(b"\xff") == "74======"  # 11111 111(00)
    assert encode(b"\x01") == "AE======"  # 00000 001(00)
    assert encode(b"\x00") == "AA======"
    assert encode(b"\xff\xff") == "777Q===="  # 11111 11111 11111 1(0000)
    assert encode(b"\x00\x00\x00\x00\x00") == "AAAAAAAA"
    assert encode(b"\xff\xff\xff\xff\xff") == "77777777"


def test_the_output_is_upper_case_whatever_the_bytes():
    for n in range(256):
        text = encode(bytes([n, 255 - n, n ^ 0x5A]))
        assert text == text.upper()
        assert set(text) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=")


def test_every_single_byte_has_its_own_encoding():
    seen = set()
    for n in range(256):
        text = encode(bytes([n]))
        assert len(text) == 8 and text.endswith("======")
        seen.add(text[:2])
    assert len(seen) == 256
