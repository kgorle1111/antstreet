from prefixtrie import PrefixTrie


def test_a_very_long_word_does_not_hit_the_recursion_limit():
    word = "ab" * 5000
    trie = PrefixTrie()
    assert trie.insert(word) is True
    assert word in trie
    assert trie.count_prefix(word[:5000]) == 1
    assert trie.words_with_prefix("a") == [word]
    assert trie.words_with_prefix(word[:9990]) == [word]
    assert trie.longest_common_prefix() == word
    assert trie.delete(word) is True
    assert len(trie) == 0
    assert trie.words_with_prefix("") == []


def test_a_long_chain_of_nested_prefix_words():
    words = ["x" * n for n in range(1, 2001)]
    trie = PrefixTrie(words)
    assert len(trie) == 2000
    assert trie.count_prefix("x" * 1000) == 1001
    assert trie.words_with_prefix("x" * 1990) == words[1989:]
    assert trie.longest_common_prefix() == "x"
    assert trie.delete("x" * 2000) is True
    assert trie.delete("x" * 1) is True
    assert trie.longest_common_prefix() == "xx"


def test_many_words_stay_fast_and_correct():
    words = [f"{n:05d}" for n in range(0, 30000, 3)]
    trie = PrefixTrie(words)
    assert len(trie) == 10000
    assert trie.count_prefix("00") == len([w for w in words if w.startswith("00")])
    assert trie.words_with_prefix("1234") == [w for w in words if w.startswith("1234")]
    for word in words[::2]:
        assert trie.delete(word) is True
    assert len(trie) == 5000
    assert trie.words_with_prefix("") == words[1::2]
