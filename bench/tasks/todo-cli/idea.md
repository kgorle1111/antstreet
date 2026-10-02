Create three Python modules (standard library only) for a small in-memory to-do list driven by text commands: `core.py` holds the list, `parse.py` turns a command line into a structured command, and `shell.py` runs a command line against a list and returns the reply text. There is no file or terminal I/O.

`core.py` provides:

    Item(id: int, text: str, priority: int, tags: tuple[str, ...], done: bool)    # frozen dataclass
    TodoList()
    add(text: str, priority: int = 2, tags: Iterable[str] = ()) -> int
    done(item_id: int) -> None
    remove(item_id: int) -> None
    get(item_id: int) -> Item
    items(status: str = "open", tag: str | None = None) -> list[Item]
    len(todos) -> int

`parse.py` provides:

    ParseError(ValueError)
    Command(name: str, item_id: int | None = None, text: str | None = None, priority: int | None = None, tags: tuple[str, ...] = (), status: str | None = None)    # frozen dataclass
    parse_command(line: str) -> Command

`shell.py` provides:

    run_command(todos: TodoList, line: str) -> str

Core:

1. `add` returns the new item's id. Ids are the integers 1, 2, 3, ... in the order of adding, and an id is never reused, even after the item is removed. `len(todos)` is the number of items held, open or done.
2. `text` must be a `str` that is not empty after stripping leading and trailing whitespace and contains no newline, otherwise `ValueError`. The stored text is the stripped text. `priority` must be an `int` from 1 (most urgent) to 3 (a `bool` is rejected), otherwise `ValueError`.
3. Each tag is a `str`. It is stripped and lower-cased, and the result must be made only of the characters `a-z`, `0-9`, `_` and `-` and be non-empty, otherwise `ValueError`. The item's `tags` is a tuple of the normalised tags in the order given, with repeats dropped (the first one stays). An invalid `add` changes nothing and uses no id.
4. `get(item_id)` returns the `Item`. `done(item_id)` marks the item done; doing it again is allowed and changes nothing. `remove(item_id)` deletes the item. All three raise `KeyError` for an id that does not exist (never added or removed).
5. `items(status="open", tag=None)` returns a new list of items. `status` is `"open"`, `"done"` or `"all"`, otherwise `ValueError`. If `tag` is given it is stripped and lower-cased and only items having that tag are returned. The list is ordered by priority, 1 first, and by id, lowest first, within one priority.

Parsing:

6. `parse_command(line)` splits `line` on whitespace. The first word is the command name, compared case-insensitively and stored in lower case in `Command.name`. An empty or blank line, an unknown name, or a `line` that is not a `str` raises `ParseError`.
7. `add <words>`: a word that starts with `#` and has at least one more character is a tag (the tag is the word without the `#`, as written); a word that is `!` followed by one or more ASCII digits is the priority; every other word, including a lone `#` or a lone `!`, is text. The text is the text words joined with single spaces. The result is `Command("add", text=..., priority=..., tags=...)` with `priority` `None` when none was given. `ParseError` if there is no text word, if a priority is given twice, or if the priority number is not 1, 2 or 3 (`!0`, `!4`, `!10`). Tags and text words may be mixed in any order.
8. `done <id>` and `rm <id>` take exactly one word made only of ASCII digits and denoting an integer of at least 1 (leading zeros are fine: `007` is 7). The result is `Command("done", item_id=n)` or `Command("rm", item_id=n)`. Anything else (no argument, two arguments, `0`, `-1`, `x`, `1.5`) raises `ParseError`.
9. `list [open|done|all] [#tag]`: up to one status word (case-insensitive, stored in lower case) and up to one tag word, in either order. The result is `Command("list", status=..., tags=(...))` where `status` is `"open"` when none was given and `tags` holds the one tag (without the `#`, as written) or is empty. A second status word, a second tag, or any other word raises `ParseError`.

Running:

10. `run_command(todos, line)` parses the line, applies it to `todos` and returns the reply as a string without a trailing newline. It never raises for a bad command or a bad id, it returns a reply that starts with `Error: ` instead and leaves the list unchanged. That covers every `ValueError` (including `ParseError`) raised while parsing or applying the command, and an id that does not exist, whose reply is exactly `Error: no item #<id>`.
11. `add` replies `Added #<id>: <text>`, with the priority and tags passed on to `TodoList.add` (a missing priority means the default 2). `done` replies `Done #<id>: <text>` (also when it was already done) and `rm` replies `Removed #<id>: <text>`.
12. `list` returns one line per item in the order of `TodoList.items` for the given status and tag, each `[ ] #<id> (p<priority>) <text>` for an open item or `[x] #<id> (p<priority>) <text>` for a done item, followed for every tag by a space and `#<tag>`, in tag order. Lines are joined with `"\n"`. When there are no items the reply is `No items.`.

Example session: `add buy milk !1 #home #Errand` replies `Added #1: buy milk`; `list` then replies `[ ] #1 (p1) buy milk #home #errand`; `done 1` replies `Done #1: buy milk`; `list` replies `No items.`; `list done` replies `[x] #1 (p1) buy milk #home #errand`.
