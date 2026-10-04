Create a Python module `undoredo.py` (standard library only) with one class:

    TextBuffer(initial: str = "", merge_window: float = 1.0, max_steps: int = 100)

    text -> str                                  # property
    insert(pos: int, text: str, now: float = 0.0) -> None
    delete(start: int, end: int, now: float = 0.0) -> None
    undo() -> bool
    redo() -> bool
    can_undo -> bool                             # property
    can_redo -> bool                             # property

It is the editing core of a text editor: a string with an undo and redo history. It never reads
a clock: `now` is the time of an edit in seconds, given by the caller, and does not go backwards
between edits.

1. `initial` is the starting text; it is not an edit and cannot be undone. `merge_window` must be
   at least 0 and `max_steps` a whole number of at least 1, otherwise the constructor raises
   `ValueError`. A new buffer has `can_undo` and `can_redo` both `False`.
2. `insert(pos, text, now)` puts `text` at index `pos` of the current text, so the characters from
   `pos` on move right. `text` must be a non-empty `str` (else `ValueError`) and `pos` a whole number
   from 0 to `len(self.text)` inclusive (else `IndexError`).
3. `delete(start, end, now)` removes the characters at indexes `start` up to but not including
   `end`. It needs `0 <= start <= end <= len(self.text)`, otherwise `IndexError`. With
   `start == end` it does nothing at all: no history entry, the redo history is kept and nothing
   else about the buffer changes. A call that raises changes nothing.
4. The history is a list of steps. Each edit that changes the text adds one step, except a merged
   insert (see 6). `undo()` reverses the most recent step in full, keeps it for `redo()` and
   returns `True`; with no step to undo it returns `False` and changes nothing. `redo()` applies
   the most recently undone step again and returns `True`, or `False` if there is none.
   `can_undo` and `can_redo` say whether the calls would return `True`.
5. Any edit that changes the text (an insert, or a delete with `start < end`) discards every step
   that could still be redone.
6. Typing merges. An `insert` joins the most recent step, becoming part of it instead of adding a
   new one, when all of these hold: that step is an insert, it is still open (see 7), the new
   text goes exactly where that step's text ends (`pos` equals the step's start index plus the
   length of everything it has inserted so far), and `now` minus the `now` of the latest insert
   that joined that step is at most `merge_window` (exactly `merge_window` merges). Each
   insert that joins renews the window for the next one. A merged step is undone and redone as one.
   Otherwise the insert adds a new step. A delete never merges with anything.
7. A step is open only until the next edit that is not merged into it, or until the next `undo()`
   or `redo()`; an `undo` or `redo` closes every step, so the first insert after it always adds a new
   step, however close in position and time it is. A delete with `start < end` closes the step it
   follows.
8. At most `max_steps` steps are kept for `undo`: when adding a step would make more, the oldest
   one is dropped for good. A merged insert adds no step.
