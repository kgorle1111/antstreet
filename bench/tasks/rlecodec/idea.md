Create a Python module `rlecodec.py` (standard library only) that compresses text with run-length encoding, where the encoded form must be unambiguous even when the text itself contains digits and backslashes. It provides two functions:

    encode(text: str) -> str
    decode(text: str, max_output: int = 1_000_000) -> str

In this text, examples are written as Python string literals, and "digit" always means one of the ASCII characters `0` to `9` (a digit of another script, such as U+0663 ARABIC-INDIC DIGIT THREE, is an ordinary character).

The encoded form is a sequence of tokens. Each token is a count followed by a unit:

- The count is a decimal number of one or more ASCII digits, at least 1, with no leading zeros (`7` and `120` are fine; `0`, `07` and `00` are not).
- The unit is one character of the text. A character that is neither a digit nor a backslash stands for itself. A digit or a backslash is written with a backslash in front of it, so the unit for `7` is `\7` and the unit for a backslash is `\\`.

1. `encode(text)` replaces every maximal run of the same character with one token: the length of the run, then the unit for that character. `'aaabcc'` becomes `'3a1b2c'`, `'a'` becomes `'1a'`, `''` becomes `''`, `'11'` becomes `'2\\1'` (the characters `2`, backslash, `1`), the single character backslash becomes `'1\\\\'` (the characters `1`, backslash, backslash), and `'a\n\n'` becomes `'1a2\n'`. Every other character, including line breaks, spaces and characters of any script, is written as it is. A text that is not a `str` raises `TypeError`.
2. `decode(text, max_output=1_000_000)` is the reverse: it reads tokens until the end of the text and joins the units repeated by their counts. `'3a1b2c'` becomes `'aaabcc'`, `'2\\1'` becomes `'11'`, and `''` becomes `''`. Decoding accepts any sequence of valid tokens, not only what `encode` writes: `'1a1a'` is `'aa'` and `'2a3a'` is `'aaaaa'`.
3. A text that is not valid raises `ValueError`: a unit with no count in front of it (`'a'`, `'abc'`, `'\\1'`), a count of `0` or with a leading zero (`'0a'`, `'01a'`), a count with no unit after it (`'3'`, `'3a2'`), a backslash at the end of the text, and a backslash followed by a character that is not a digit or a backslash (`'1\\a'`).
4. `max_output` is the longest decoded text allowed, in characters. When the counts read so far add up to more than `max_output`, `decode` raises `ValueError` at once, before the repeated text is built, so that `decode('99999999999999a')` fails quickly instead of using all the memory. A total equal to `max_output` is fine. `max_output` must be an `int` (not a `bool`), else `TypeError`, and not below 0, else `ValueError`. A `text` that is not a `str` raises `TypeError`.
5. For every `str` `s` whose length is at most `max_output`, `decode(encode(s), max_output)` equals `s`.
