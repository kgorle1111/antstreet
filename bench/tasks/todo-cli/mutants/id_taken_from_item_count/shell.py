# Same as the reference; the bug is in core.py: A new id is the number of items plus one, so ids are reused after a remove.
from parse import parse_command


def _line(item):
    mark = "x" if item.done else " "
    tags = "".join(f" #{tag}" for tag in item.tags)
    return f"[{mark}] #{item.id} (p{item.priority}) {item.text}{tags}"


def _apply(todos, command):
    if command.name == "add":
        priority = 2 if command.priority is None else command.priority
        item_id = todos.add(command.text, priority, command.tags)
        return f"Added #{item_id}: {todos.get(item_id).text}"
    if command.name == "list":
        tag = command.tags[0] if command.tags else None
        lines = [_line(i) for i in todos.items(command.status, tag)]
        return "\n".join(lines) or "No items."
    try:
        item = todos.get(command.item_id)
    except KeyError:
        return f"Error: no item #{command.item_id}"
    if command.name == "done":
        todos.done(item.id)
        return f"Done #{item.id}: {item.text}"
    todos.remove(item.id)
    return f"Removed #{item.id}: {item.text}"


def run_command(todos, line):
    try:
        return _apply(todos, parse_command(line))
    except ValueError as exc:
        return f"Error: {exc}"
