Create a Python module `prefixtrie.py` (standard library only) with one class:

    PrefixTrie(words: Iterable[str] = ())

    insert(word) -> bool
    delete(word) -> bool
    count_prefix(prefix) -> int
    words_with_prefix(prefix) -> list[str]
    longest_common_prefix() -> str
    len(trie) -> int
    word in trie -> bool

It stores a set of words so that questions about prefixes can be answered without scanning every
word.

1. Words are non-empty strings and are case-sensitive. `insert("")` and `delete("")` raise
   `ValueError`. `insert`, `delete`, `count_prefix` and `words_with_prefix` raise `TypeError` when
   their argument is not a `str`. `word in trie` never raises: it is `False` for `""` and for any
   argument that is not a stored string.
2. `PrefixTrie(words)` inserts each word in order, ignoring repeats. An empty string among them
   raises `ValueError`.
3. `insert(word)` returns `True` when the word was added and `False` when it was already stored
   (nothing changes). `len(trie)` is the number of distinct stored words.
4. `delete(word)` returns `True` when the word was stored and is now removed, and `False` when it
   was not stored. A string that is only a prefix of stored words is not stored: `delete("car")`
   returns `False` and changes nothing when only `"cart"` is stored. Deleting a stored word that is
   a prefix of other stored words removes just that word: after `delete("car")` with `"car"` and
   `"cart"` stored, `"cart"` is still there. Nothing of a deleted word lingers: later answers are
   exactly those of a trie that never held it.
5. `count_prefix(prefix)` is the number of stored words that start with `prefix`. A word starts
   with itself, so a stored `"car"` counts for the prefix `"car"`. The prefix `""` matches every
   word, so it gives `len(trie)`. A prefix that no word starts with gives `0`.
6. `words_with_prefix(prefix)` returns a new list of those same words in ascending order as Python
   compares strings (so a word comes before the longer words that extend it). It is `[]` when there
   are none, and every word for the prefix `""`.
7. `longest_common_prefix()` returns the longest string that every stored word starts with, and
   `""` when the trie is empty. For one stored word it is that word. It stops at the end of a
   stored word: for `"car"` and `"cart"` it is `"car"`.
8. Words may be thousands of characters long. No method may hit Python's recursion limit.
