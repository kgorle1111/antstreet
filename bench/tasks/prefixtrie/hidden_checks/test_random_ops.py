import random

from prefixtrie import PrefixTrie


def lcp(words):
    if not words:
        return ""
    first, last = min(words), max(words)
    n = 0
    while n < len(first) and n < len(last) and first[n] == last[n]:
        n += 1
    return first[:n]


def test_random_operations_match_a_set_of_strings():
    rng = random.Random(7)
    for _ in range(25):
        trie = PrefixTrie()
        model = set()
        for _ in range(200):
            word = "".join(rng.choice("abc") for _ in range(rng.randint(1, 5)))
            action = rng.choice(["insert", "insert", "delete", "query"])
            if action == "insert":
                assert trie.insert(word) == (word not in model)
                model.add(word)
            elif action == "delete":
                assert trie.delete(word) == (word in model)
                model.discard(word)
            else:
                prefix = word[: rng.randint(0, len(word))]
                expected = sorted(w for w in model if w.startswith(prefix))
                assert trie.words_with_prefix(prefix) == expected
                assert trie.count_prefix(prefix) == len(expected)
            assert len(trie) == len(model)
            assert (word in trie) == (word in model)
            assert trie.longest_common_prefix() == lcp(model)
