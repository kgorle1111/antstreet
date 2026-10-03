from prefixtrie import PrefixTrie

WORDS = ["carton", "dog", "car", "care", "do", "cart", "dot", "b"]


def test_returns_matching_words_in_ascending_order():
    trie = PrefixTrie(WORDS)
    assert trie.words_with_prefix("car") == ["car", "care", "cart", "carton"]
    assert trie.words_with_prefix("do") == ["do", "dog", "dot"]


def test_a_word_comes_before_the_words_that_extend_it():
    trie = PrefixTrie(["abc", "ab", "abd", "a", "abcd"])
    assert trie.words_with_prefix("a") == ["a", "ab", "abc", "abcd", "abd"]
    assert trie.words_with_prefix("ab") == ["ab", "abc", "abcd", "abd"]


def test_empty_prefix_returns_every_word_sorted():
    trie = PrefixTrie(WORDS)
    assert trie.words_with_prefix("") == sorted(WORDS)


def test_no_match_returns_empty_list():
    trie = PrefixTrie(WORDS)
    assert trie.words_with_prefix("z") == []
    assert trie.words_with_prefix("cartons") == []
    assert PrefixTrie().words_with_prefix("a") == []


def test_ordering_is_by_code_point_not_by_insertion_or_length():
    words = ["b", "B", "a", "A", "_", "~", "10", "9", "z"]
    trie = PrefixTrie(words)
    assert trie.words_with_prefix("") == sorted(words)


def test_returns_a_new_list_each_call():
    trie = PrefixTrie(["a", "ab"])
    first = trie.words_with_prefix("a")
    first.clear()
    first.append("junk")
    assert trie.words_with_prefix("a") == ["a", "ab"]
    assert len(trie) == 2
