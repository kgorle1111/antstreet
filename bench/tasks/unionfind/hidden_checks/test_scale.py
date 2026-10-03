from unionfind import UnionFind


def test_a_hundred_thousand_elements_joined_in_a_chain():
    n = 100_000
    uf = UnionFind(range(n))
    for i in range(n - 1):
        assert uf.union(i, i + 1) is True
    assert uf.num_sets == 1
    assert uf.size(0) == n
    reps = {uf.find(i) for i in range(n)}
    assert len(reps) == 1
    assert uf.connected(0, n - 1)


def test_chain_joined_from_the_other_end():
    n = 100_000
    uf = UnionFind(range(n))
    for i in range(n - 1, 0, -1):
        uf.union(i, i - 1)
    assert uf.num_sets == 1
    assert len({uf.find(i) for i in range(n)}) == 1
    assert uf.size(n // 2) == n


def test_many_small_sets_then_one_merge():
    n = 60_000
    uf = UnionFind(range(n))
    for i in range(0, n, 2):
        uf.union(i, i + 1)
    assert uf.num_sets == n // 2
    for i in range(0, n - 2, 2):
        uf.union(i, i + 2)
    assert uf.num_sets == 1
    assert len(uf.groups()) == 1
    assert uf.groups()[0] == list(range(n))
