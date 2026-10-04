# An equals sign that does not start a valid escape is copied as it is instead of raising.
"""Quoted-printable decoder written by hand (RFC 2045 section 6.7, lenient on line endings)."""

import string

_HEX = frozenset(string.hexdigits)


def _escapes(line: str, out: bytearray) -> None:
    i = 0
    while i < len(line):
        if line[i] != "=":
            out.append(ord(line[i]))
            i += 1
            continue
        pair = line[i + 1 : i + 3]
        if len(pair) != 2 or not set(pair) <= _HEX:
            out.append(61)
            i += 1
            continue
        out.append(int(pair, 16))
        i += 3


def decode(text: str) -> bytes:
    if not isinstance(text, str):
        raise TypeError(f"expected str, got {type(text).__name__}")
    if not text.isascii():
        raise ValueError("quoted-printable text must be ASCII")
    out = bytearray()
    lines = text.split("\n")
    for index, line in enumerate(lines):
        last = index == len(lines) - 1
        ending = ""
        if not last:
            ending = "\n"
            if line.endswith("\r"):
                line, ending = line[:-1], "\r\n"
        if line.endswith("="):  # soft line break: join with the next line, keep the spaces
            _escapes(line[:-1], out)
            continue
        _escapes(line.rstrip(" \t"), out)
        out += ending.encode("ascii")
    return bytes(out)


def decode_str(text: str, charset: str = "utf-8") -> str:
    return decode(text).decode(charset)
