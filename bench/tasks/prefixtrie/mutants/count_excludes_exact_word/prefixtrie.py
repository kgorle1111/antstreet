# count_prefix leaves out a stored word equal to the prefix itself, counting only longer words.
from collections.abc import Iterable


class _Node:
    """`count` is the number of stored words in this node's subtree, including its own."""

    __slots__ = ("children", "count", "is_word")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.count = 0
        self.is_word = False


def _check(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected a str, got {type(value).__name__}")
    if not value and not allow_empty:
        raise ValueError("the empty string is not a word")
    return value


class PrefixTrie:
    def __init__(self, words: Iterable[str] = ()) -> None:
        self._root = _Node()
        for word in words:
            self.insert(word)

    def _find(self, prefix: str) -> _Node | None:
        node = self._root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def insert(self, word: str) -> bool:
        _check(word)
        if word in self:
            return False
        node = self._root
        node.count += 1
        for ch in word:
            node = node.children.setdefault(ch, _Node())
            node.count += 1
        node.is_word = True
        return True

    def delete(self, word: str) -> bool:
        _check(word)
        if word not in self:
            return False
        node = self._root
        node.count -= 1
        for ch in word:
            child = node.children[ch]
            child.count -= 1
            if child.count == 0:
                del node.children[ch]  # the rest of the path held only this word
                return True
            node = child
        node.is_word = False
        return True

    def count_prefix(self, prefix: str) -> int:
        _check(prefix, allow_empty=True)
        node = self._find(prefix)
        return 0 if node is None else node.count - node.is_word

    def words_with_prefix(self, prefix: str) -> list[str]:
        _check(prefix, allow_empty=True)
        start = self._find(prefix)
        if start is None:
            return []
        found: list[str] = []
        stack = [(start, prefix)]
        while stack:
            node, text = stack.pop()
            if node.is_word:
                found.append(text)
            for ch in sorted(node.children, reverse=True):
                stack.append((node.children[ch], text + ch))
        return found

    def longest_common_prefix(self) -> str:
        node = self._root
        chars: list[str] = []
        while len(node.children) == 1 and not node.is_word:
            ((ch, node),) = node.children.items()
            chars.append(ch)
        return "".join(chars)

    def __len__(self) -> int:
        return self._root.count

    def __contains__(self, word: object) -> bool:
        if not isinstance(word, str) or not word:
            return False
        node = self._find(word)
        return node is not None and node.is_word
