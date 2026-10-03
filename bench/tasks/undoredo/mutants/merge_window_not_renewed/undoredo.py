# A merged insert does not renew the window, so it is measured from the first insert only.
class TextBuffer:
    def __init__(self, initial: str = "", merge_window: float = 1.0, max_steps: int = 100) -> None:
        if merge_window < 0:
            raise ValueError("merge_window must be at least 0")
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("max_steps must be a whole number of at least 1")
        self._text = initial
        self._window = merge_window
        self._max = max_steps
        # A step is [kind, index, text] where kind is "ins" or "del".
        self._undo: list[list] = []
        self._redo: list[list] = []
        # Time of the latest insert in the open top step; None when no step is open.
        self._last: float | None = None

    @property
    def text(self) -> str:
        return self._text

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _push(self, step: list) -> None:
        self._undo.append(step)
        if len(self._undo) > self._max:
            self._undo.pop(0)

    def insert(self, pos: int, text: str, now: float = 0.0) -> None:
        if type(text) is not str or not text:
            raise ValueError("text must be a non-empty string")
        if type(pos) is not int or not 0 <= pos <= len(self._text):
            raise IndexError(f"position {pos!r} is outside the text")
        top = self._undo[-1] if self._undo else None
        if (
            self._last is not None
            and top is not None
            and top[0] == "ins"
            and pos == top[1] + len(top[2])
            and now - self._last <= self._window
        ):
            top[2] += text
        else:
            self._push(["ins", pos, text])
            self._last = now
        self._text = self._text[:pos] + text + self._text[pos:]
        self._redo.clear()

    def delete(self, start: int, end: int, now: float = 0.0) -> None:
        size = len(self._text)
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= size:
            raise IndexError(f"range {start!r}:{end!r} is outside the text")
        if start == end:
            return
        removed = self._text[start:end]
        self._text = self._text[:start] + self._text[end:]
        self._push(["del", start, removed])
        self._last = None
        self._redo.clear()

    def _apply(self, step: list, forward: bool) -> None:
        kind, index, chunk = step
        if (kind == "ins") == forward:
            self._text = self._text[:index] + chunk + self._text[index:]
        else:
            self._text = self._text[:index] + self._text[index + len(chunk) :]

    def undo(self) -> bool:
        if not self._undo:
            return False
        step = self._undo.pop()
        self._apply(step, forward=False)
        self._redo.append(step)
        self._last = None
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        step = self._redo.pop()
        self._apply(step, forward=True)
        self._undo.append(step)
        self._last = None
        return True
