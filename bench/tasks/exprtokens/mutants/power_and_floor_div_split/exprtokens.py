# ** and // are missing from the two-character operators, so each comes out as two one-character operators.
class TokenError(ValueError):
    def __init__(self, message: str, position: int) -> None:
        super().__init__(f"{message} at position {position}")
        self.position = position


_TWO_CHAR_OPS = ("==", "!=", "<=", ">=")
_ONE_CHAR_OPS = "+-*/%^<>"
_PUNCTUATION = {"(": "LPAREN", ")": "RPAREN", ",": "COMMA"}
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"


def _digit(src: str, i: int) -> bool:
    return i < len(src) and "0" <= src[i] <= "9"


def _digits_end(src: str, i: int) -> int:
    while _digit(src, i):
        i += 1
    return i


def _number_end(src: str, i: int) -> int:
    j = _digits_end(src, i)
    if j < len(src) and src[j] == "." and _digit(src, j + 1):
        j = _digits_end(src, j + 1)
    if j < len(src) and src[j] in "eE":
        k = j + 1
        if k < len(src) and src[k] in "+-":
            k += 1
        if _digit(src, k):
            j = _digits_end(src, k)
    return j


def tokenize(src: str) -> list[tuple[str, str, int]]:
    if not isinstance(src, str):
        raise ValueError("src must be a str")
    tokens: list[tuple[str, str, int]] = []
    i = 0
    while i < len(src):
        ch = src[i]
        if ch in " \t\n\r":
            i += 1
            continue
        if _digit(src, i) or (ch == "." and _digit(src, i + 1)):
            end, kind = _number_end(src, i), "NUM"
        elif ch in _LETTERS:
            end = i + 1
            while end < len(src) and (src[end] in _LETTERS or _digit(src, end)):
                end += 1
            kind = "IDENT"
        elif src[i : i + 2] in _TWO_CHAR_OPS:
            end, kind = i + 2, "OP"
        elif ch in _ONE_CHAR_OPS:
            end, kind = i + 1, "OP"
        elif ch in _PUNCTUATION:
            end, kind = i + 1, _PUNCTUATION[ch]
        else:
            raise TokenError(f"unexpected character {ch!r}", i)
        tokens.append((kind, src[i:end], i))
        i = end
    return tokens
