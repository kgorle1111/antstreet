Create a Python module `qpdecode.py` (standard library only) that decodes quoted-printable text (the transfer encoding of email bodies, RFC 2045) by hand. Do not import `quopri` or `binascii`; the module is judged on behaviour only, but the point is to write the decoder yourself. It provides two functions:

    decode(text: str) -> bytes
    decode_str(text: str, charset: str = "utf-8") -> str

In this text, examples of input are written as Python string literals.

Rules for `decode`:

1. `text` may only hold ASCII characters (code points 0 to 127); any other character raises `ValueError`. A `text` that is not a `str` raises `TypeError`. The result is always `bytes`.
2. A line ends at `\n` or `\r\n`. These line breaks are kept exactly as they are in the text: `'a\r\nb\nc'` decodes to `b'a\r\nb\nc'`.
3. `=` followed by two hexadecimal digits, in upper or lower case, stands for the byte with that value: `'caf=C3=A9'` is `b'caf\xc3\xa9'`, `'=3D'` and `'=3d'` are `b'='`, `'=0D=0A'` is the two bytes `\r\n` (not a line break of the text).
4. `=` at the end of a line (just before `\n` or `\r\n`) or at the very end of the text is a soft line break: the `=` and the line break after it are removed and the next line continues the same line. `'abc=\r\ndef'` and `'abc=\ndef'` decode to `b'abcdef'`, and `'abc='` to `b'abc'`.
5. Any other `=` raises `ValueError`: `=` followed by fewer than two characters on its line, or by a character that is not a hexadecimal digit (`'=G1'`, `'=1'`, `'=1G'`, `'= '`, `'=='`, `'a= \r\nb'` (the `=` is followed by a space, so it is not a soft line break), `'a=\r'` with a carriage return that is not part of `\r\n`).
6. Spaces and tabs at the end of a line are dropped (mail transports may add them). This applies to every line that does not end in a soft line break, including the last line of the text and a line that holds only whitespace: `'a  \r\nb\t\n'` decodes to `b'a\r\nb\n'`, and `'   '` decodes to `b''`. Whitespace written as `=20` or `=09` is not dropped: `'a=20'` is `b'a '` and `'a =20'` is `b'a  '`. Whitespace before a soft line break is content and is kept: `'a  =\r\nb'` is `b'a  b'`. Whitespace inside a line is always kept.
7. Every other ASCII character stands for its own byte.

`decode_str(text, charset="utf-8")` is `decode(text)` read as text in that charset. Bytes that are not valid in the charset raise `ValueError`, and an unknown charset name raises `LookupError`. The same errors as `decode` apply to `text`.
