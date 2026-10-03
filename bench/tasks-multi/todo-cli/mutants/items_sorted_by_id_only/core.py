# items() orders by id only and ignores priority.
import re
from dataclasses import dataclass, replace

_TAG_RE = re.compile(r"[a-z0-9_-]+")
_STATUSES = ("open", "done", "all")


@dataclass(frozen=True)
class Item:
    id: int
    text: str
    priority: int
    tags: tuple[str, ...]
    done: bool


def _normal_tag(tag):
    if not isinstance(tag, str):
        raise ValueError("a tag must be a str")
    tag = tag.strip().lower()
    if not _TAG_RE.fullmatch(tag):
        raise ValueError(f"invalid tag {tag!r}")
    return tag


class TodoList:
    def __init__(self):
        self._items = {}
        self._next_id = 1

    def add(self, text, priority=2, tags=()):
        if not isinstance(text, str) or not text.strip() or "\n" in text:
            raise ValueError("text must be a non-empty single-line str")
        if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 3:
            raise ValueError("priority must be 1, 2 or 3")
        normal = tuple(dict.fromkeys(_normal_tag(t) for t in tags))
        item = Item(self._next_id, text.strip(), priority, normal, False)
        self._items[item.id] = item
        self._next_id += 1
        return item.id

    def get(self, item_id):
        return self._items[item_id]

    def done(self, item_id):
        self._items[item_id] = replace(self._items[item_id], done=True)

    def remove(self, item_id):
        del self._items[item_id]

    def items(self, status="open", tag=None):
        if status not in _STATUSES:
            raise ValueError(f"status must be one of {_STATUSES}")
        wanted = None if tag is None else _normal_tag(tag)
        chosen = [
            i
            for i in self._items.values()
            if (status == "all" or i.done == (status == "done"))
            and (wanted is None or wanted in i.tags)
        ]
        return sorted(chosen, key=lambda i: i.id)

    def __len__(self):
        return len(self._items)
