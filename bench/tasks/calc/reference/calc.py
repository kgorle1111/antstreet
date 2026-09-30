import operator
import re

_TOKEN = re.compile(r"([0-9]+(?:\.[0-9]+)?)|([-+*/()])|([ \t\r\n]+)|(.)", re.DOTALL)
_BINARY = {"+": operator.add, "-": operator.sub, "*": operator.mul, "/": operator.truediv}


def _tokenize(text: str) -> list[int | float | str]:
    tokens: list[int | float | str] = []
    for match in _TOKEN.finditer(text):
        number, symbol, _space, other = match.groups()
        if number is not None:
            tokens.append(float(number) if "." in number else int(number))
        elif symbol is not None:
            tokens.append(symbol)
        elif other is not None:
            raise ValueError(f"unexpected character {other!r}")
    return tokens


class _Parser:
    """Recursive descent that emits postfix, so long chains never deepen the evaluation stack."""

    def __init__(self, tokens: list[int | float | str]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.postfix: list[int | float | str] = []

    def _peek(self) -> int | float | str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _take(self) -> int | float | str | None:
        token = self._peek()
        self.pos += 1
        return token

    def parse(self) -> list[int | float | str]:
        self._expr()
        if self.pos != len(self.tokens):
            raise ValueError("unexpected token after expression")
        return self.postfix

    def _expr(self) -> None:
        self._term()
        while self._peek() in ("+", "-"):
            op = self._take()
            self._term()
            self.postfix.append(op)

    def _term(self) -> None:
        self._unary()
        while self._peek() in ("*", "/"):
            op = self._take()
            self._unary()
            self.postfix.append(op)

    def _unary(self) -> None:
        if self._peek() in ("+", "-"):
            op = self._take()
            self._unary()
            if op == "-":
                self.postfix.append("neg")
        else:
            self._primary()

    def _primary(self) -> None:
        token = self._take()
        if isinstance(token, int | float):
            self.postfix.append(token)
        elif token == "(":
            self._expr()
            if self._take() != ")":
                raise ValueError("expected ')'")
        else:
            raise ValueError("expected a number or '('")


def evaluate(expression: str) -> int | float:
    if not isinstance(expression, str):
        raise ValueError(f"expression must be a string, got {type(expression).__name__}")
    stack: list[int | float] = []
    for item in _Parser(_tokenize(expression)).parse():
        if not isinstance(item, str):
            stack.append(item)
        elif item == "neg":
            stack.append(-stack.pop())
        else:
            right = stack.pop()
            left = stack.pop()
            stack.append(_BINARY[item](left, right))
    return stack[0]
