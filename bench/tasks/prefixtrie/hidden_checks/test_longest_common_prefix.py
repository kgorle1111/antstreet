from prefixtrie import PrefixTrie


def test_common_prefix_of_several_words():
    assert PrefixTrie(["flower", "flow", "flight"]).longest_common_prefix() == "fl"
    assert PrefixTrie(["interview", "internet", "interval"]).longest_common_prefix() == "inter"


def test_empty_trie_gives_empty_string():
    assert PrefixTrie().longest_common_prefix() == ""


def test_single_word_is_its_own_common_prefix():
    assert PrefixTrie(["hello"]).longest_common_prefix() == "hello"
    assert PrefixTrie(["x"]).longest_common_prefix() == "x"


def test_stops_at_the_end_of_a_stored_word():
    assert PrefixTrie(["car", "cart"]).longest_common_prefix() == "car"
    assert PrefixTrie(["cart", "car", "carton"]).longest_common_prefix() == "car"
    assert PrefixTrie(["a", "abc"]).longest_common_prefix() == "a"


def test_no_shared_first_letter_gives_empty_string():
    assert PrefixTrie(["dog", "racecar", "car"]).longest_common_prefix() == ""


def test_identical_words_are_one_word():
    assert PrefixTrie(["same", "same", "same"]).longest_common_prefix() == "same"


def test_follows_deletes_and_inserts():
    trie = PrefixTrie(["flower", "flow", "flight"])
    trie.delete("flight")
    assert trie.longest_common_prefix() == "flow"
    trie.delete("flow")
    assert trie.longest_common_prefix() == "flower"
    trie.insert("fly")
    assert trie.longest_common_prefix() == "fl"
    trie.delete("flower")
    assert trie.longest_common_prefix() == "fly"
