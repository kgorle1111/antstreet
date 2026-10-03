from prefixtrie import PrefixTrie

WORDS = ["car", "cart", "carton", "care", "dog", "do", "dot"]


def test_counts_words_starting_with_the_prefix():
    trie = PrefixTrie(WORDS)
    assert trie.count_prefix("ca") == 4
    assert trie.count_prefix("cart") == 2
    assert trie.count_prefix("do") == 3
    assert trie.count_prefix("dot") == 1
    assert trie.count_prefix("d") == 3


def test_a_stored_word_counts_for_itself():
    trie = PrefixTrie(["car"])
    assert trie.count_prefix("car") == 1
    assert trie.count_prefix("ca") == 1


def test_empty_prefix_counts_everything():
    trie = PrefixTrie(WORDS)
    assert trie.count_prefix("") == 7 == len(trie)
    assert PrefixTrie().count_prefix("") == 0


def test_unmatched_prefixes_count_zero():
    trie = PrefixTrie(WORDS)
    assert trie.count_prefix("x") == 0
    assert trie.count_prefix("cartons") == 0
    assert trie.count_prefix("cab") == 0
    assert trie.count_prefix("Car") == 0


def test_counts_follow_inserts_and_deletes():
    trie = PrefixTrie()
    for i, word in enumerate(["to", "tea", "ten", "ted", "tell"], start=1):
        trie.insert(word)
        assert trie.count_prefix("t") == i
    assert trie.count_prefix("te") == 4
    trie.insert("tea")
    assert trie.count_prefix("te") == 4
    trie.delete("ten")
    assert trie.count_prefix("te") == 3
    assert trie.count_prefix("ten") == 0
    assert trie.count_prefix("t") == 4
