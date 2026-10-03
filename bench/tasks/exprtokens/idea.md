Create a Python module `exprtokens.py` (standard library only) with one function and one exception class:

    tokenize(src: str) -> list[tuple[str, str, int]]
    class TokenError(ValueError)

`tokenize` splits the text of an arithmetic expression into tokens. Each token is a tuple `(kind, text, position)`: `kind` is one of the strings `"NUM"`, `"IDENT"`, `"OP"`, `"LPAREN"`, `"RPAREN"`, `"COMMA"`; `text` is the token exactly as written in `src`; `position` is the zero-based index in `src` of the token's first character. Tokens are returned in order. In this text, examples of input are written as Python string literals.

1. A space, tab, `\n` or `\r` between tokens is skipped and never makes a token. Tokens need no separators: `'2x+3'` gives `NUM 2` at 0, `IDENT x` at 1, `OP +` at 2, `NUM 3` at 3. Empty text, or text of only such whitespace, gives `[]`.
2. A `NUM` is one of: one or more ASCII digits (`12`); digits, `.` and one or more digits (`3.5`); or `.` and one or more digits (`.5`). It may then be followed by an exponent: `e` or `E`, an optional `+` or `-`, and one or more digits (`1e5`, `2.5E-3`). The exponent is part of the number only when all of it is present: in `'2e'` the number is `2` and the `e` is an `IDENT`, and in `'2e+'` they are `NUM 2`, `IDENT e` and `OP +`. A `.` that is not followed by a digit does not belong to a number, so `'5.'` is an error. The longest match is taken: `'1.5.2'` gives `NUM 1.5` and `NUM .2`. A number has no sign: `'-5'` is `OP -` and `NUM 5`.
3. An `IDENT` is an ASCII letter or `_`, followed by any number of ASCII letters, digits and `_`. `'x1_y'` is one identifier. A digit cannot start one, and a non-ASCII letter is not part of one.
4. An `OP` is one of the single characters `+ - * / % ^ < >` or one of the two-character operators `** // == != <= >=`. Two-character operators win over one-character ones: `'**'` is one `OP **`, `'<='` is one `OP <=`, and `'* *'` (with a space) is two `OP *`. `'<>'` is `OP <` then `OP >`. A lone `=` or a lone `!` is not an operator.
5. `(` is a `LPAREN`, `)` is a `RPAREN`, `,` is a `COMMA`; the `text` is that one character.
6. Any other character is an error: `tokenize` raises `TokenError` and sets its attribute `position` (an `int`) to the index of the first character that cannot start or continue a valid token. So `'1 $ 2'` has position 2, `'5.'` has position 1, `'a = b'` has position 2, and `'x!'` has position 1. `TokenError` is a subclass of `ValueError` and is defined in the module.
7. An argument that is not a `str` raises `ValueError` (a plain one, not a `TokenError`).
