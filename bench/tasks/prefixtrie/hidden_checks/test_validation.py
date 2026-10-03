import pytest
from prefixtrie import PrefixTrie


def test_empty_word_is_rejected_by_insert_and_delete():
    trie = PrefixTrie(["a"])
    with pytest.raises(ValueError):
        trie.insert("")
    with pytest.raises(ValueError):
        trie.delete("")
    assert len(trie) == 1


def test_empty_word_in_constructor_is_rejected():
    with pytest.raises(ValueError):
        PrefixTrie(["a", "", "b"])


@pytest.mark.parametrize("bad", [5, None, b"abc", ("a",), 1.5])
def test_non_string_arguments_raise_type_error(bad):
    trie = PrefixTrie(["a"])
    with pytest.raises(TypeError):
        trie.insert(bad)
    with pytest.raises(TypeError):
        trie.delete(bad)
    with pytest.raises(TypeError):
        trie.count_prefix(bad)
    with pytest.raises(TypeError):
        trie.words_with_prefix(bad)
    assert len(trie) == 1


def test_rejected_calls_leave_the_trie_unchanged():
    trie = PrefixTrie(["car", "cart"])
    for call in (lambda: trie.insert(""), lambda: trie.delete(""), lambda: trie.insert(3)):
        with pytest.raises((ValueError, TypeError)):
            call()
    assert trie.words_with_prefix("") == ["car", "cart"]
    assert trie.count_prefix("") == 2


def test_empty_prefix_is_allowed_for_queries():
    trie = PrefixTrie(["a"])
    assert trie.count_prefix("") == 1
    assert trie.words_with_prefix("") == ["a"]


def test_in_never_raises():
    trie = PrefixTrie(["a"])
    assert ("" in trie) is False
    assert (5 in trie) is False
    assert (["a"] in trie) is False
