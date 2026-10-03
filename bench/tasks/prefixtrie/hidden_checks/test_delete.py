from prefixtrie import PrefixTrie


def test_delete_returns_true_when_removed_and_false_when_absent():
    trie = PrefixTrie(["apple", "app"])
    assert trie.delete("app") is True
    assert trie.delete("app") is False
    assert trie.delete("nope") is False
    assert len(trie) == 1
    assert "app" not in trie
    assert "apple" in trie


def test_deleting_a_prefix_word_keeps_its_extensions():
    trie = PrefixTrie(["car", "cart", "carton", "care"])
    assert trie.delete("car") is True
    assert trie.words_with_prefix("car") == ["care", "cart", "carton"]
    assert trie.count_prefix("car") == 3
    assert "cart" in trie and "carton" in trie and "care" in trie


def test_deleting_an_extension_keeps_the_prefix_word():
    trie = PrefixTrie(["car", "cart", "carton"])
    assert trie.delete("carton") is True
    assert "car" in trie and "cart" in trie
    assert trie.words_with_prefix("car") == ["car", "cart"]
    assert trie.count_prefix("carto") == 0


def test_a_string_that_is_only_a_prefix_is_not_deletable():
    trie = PrefixTrie(["cart"])
    assert trie.delete("car") is False
    assert trie.delete("c") is False
    assert len(trie) == 1
    assert trie.words_with_prefix("") == ["cart"]
    assert trie.count_prefix("ca") == 1


def test_a_string_longer_than_a_stored_word_is_not_deletable():
    trie = PrefixTrie(["car"])
    assert trie.delete("cart") is False
    assert "car" in trie
    assert len(trie) == 1


def test_nothing_lingers_after_deleting_every_word():
    trie = PrefixTrie(["alpha", "alphabet", "beta"])
    for word in ["alphabet", "alpha", "beta"]:
        assert trie.delete(word) is True
    assert len(trie) == 0
    assert trie.count_prefix("") == 0
    assert trie.count_prefix("alp") == 0
    assert trie.words_with_prefix("a") == []
    assert trie.longest_common_prefix() == ""
    assert trie.insert("alpha") is True
    assert trie.words_with_prefix("") == ["alpha"]


def test_reinsert_after_delete():
    trie = PrefixTrie(["car", "cart"])
    trie.delete("car")
    assert trie.insert("car") is True
    assert trie.insert("car") is False
    assert len(trie) == 2
    assert trie.count_prefix("car") == 2
