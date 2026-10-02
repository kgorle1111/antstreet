from prefixtrie import PrefixTrie


def test_new_trie_is_empty():
    trie = PrefixTrie()
    assert len(trie) == 0
    assert "a" not in trie
    assert trie.words_with_prefix("") == []


def test_insert_returns_true_for_new_words_and_false_for_repeats():
    trie = PrefixTrie()
    assert trie.insert("car") is True
    assert trie.insert("cart") is True
    assert trie.insert("car") is False
    assert trie.insert("cart") is False
    assert len(trie) == 2


def test_contains_is_exact_not_prefix():
    trie = PrefixTrie(["cart"])
    assert "cart" in trie
    assert "car" not in trie
    assert "carts" not in trie
    assert "" not in trie
    assert 5 not in trie
    assert None not in trie


def test_constructor_inserts_words_and_ignores_repeats():
    trie = PrefixTrie(["b", "a", "b", "ab", "a"])
    assert len(trie) == 3
    assert all(w in trie for w in ["a", "b", "ab"])
    assert PrefixTrie(w for w in ["x", "y"]).words_with_prefix("") == ["x", "y"]


def test_words_are_case_sensitive_and_unicode_safe():
    trie = PrefixTrie(["Car", "car", "café", "日本", "日本語"])
    assert len(trie) == 5
    assert "Car" in trie and "car" in trie and "CAR" not in trie
    assert trie.count_prefix("日本") == 2
    assert trie.count_prefix("caf") == 1


def test_single_character_words_and_words_with_spaces():
    trie = PrefixTrie(["a", "a b", " ", "a  b"])
    assert len(trie) == 4
    assert " " in trie
    assert trie.count_prefix("a ") == 2
    assert trie.words_with_prefix("a") == ["a", "a  b", "a b"]
