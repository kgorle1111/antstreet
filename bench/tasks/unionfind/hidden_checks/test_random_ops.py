import random

from unionfind import UnionFind


def test_random_operations_match_a_label_model():
    rng = random.Random(3)
    for _ in range(40):
        n = rng.randint(2, 25)
        order = list(range(n))
        rng.shuffle(order)
        uf = UnionFind(order)
        label = {x: x for x in order}  # naive model: every member holds its set's label
        rep = {x: x for x in order}  # label -> representative, by the stated rule
        for _ in range(60):
            a, b = rng.randrange(n), rng.randrange(n)
            la, lb = label[a], label[b]
            merged = la != lb
            assert uf.union(a, b) is merged
            if merged:
                size_a = sum(1 for v in label.values() if v == la)
                size_b = sum(1 for v in label.values() if v == lb)
                keep = rep[lb] if size_b > size_a else rep[la]
                for x, v in label.items():
                    if v == lb:
                        label[x] = la
                rep[la] = keep
            assert uf.find(a) == uf.find(b) == rep[label[a]]
            c, d = rng.randrange(n), rng.randrange(n)
            assert uf.connected(c, d) == (label[c] == label[d])
            assert uf.size(c) == sum(1 for v in label.values() if v == label[c])
            assert uf.find(c) == rep[label[c]]
        assert uf.num_sets == len(set(label.values()))
        expected = {}
        for x in order:
            expected.setdefault(label[x], []).append(x)
        assert uf.groups() == list(expected.values())
