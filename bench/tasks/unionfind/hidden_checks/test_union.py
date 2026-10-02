from unionfind import UnionFind


def test_union_returns_true_when_it_merges_and_false_when_already_joined():
    uf = UnionFind(range(5))
    assert uf.union(0, 1) is True
    assert uf.union(1, 0) is False
    assert uf.union(0, 1) is False
    assert uf.union(2, 2) is False
    assert uf.num_sets == 4


def test_connectivity_is_transitive():
    uf = UnionFind("abcdef")
    uf.union("a", "b")
    uf.union("c", "d")
    assert not uf.connected("a", "c")
    uf.union("b", "c")
    assert uf.connected("a", "d")
    assert uf.connected("d", "a")
    assert not uf.connected("a", "e")
    assert not uf.connected("e", "f")


def test_an_element_is_connected_to_itself():
    uf = UnionFind([1, 2])
    assert uf.connected(1, 1) is True
    assert uf.connected(2, 2) is True


def test_size_and_num_sets_follow_merges():
    uf = UnionFind(range(6))
    assert uf.num_sets == 6
    uf.union(0, 1)
    uf.union(2, 3)
    assert uf.num_sets == 4
    assert [uf.size(x) for x in range(6)] == [2, 2, 2, 2, 1, 1]
    uf.union(1, 3)
    assert uf.num_sets == 3
    assert [uf.size(x) for x in range(6)] == [4, 4, 4, 4, 1, 1]
    uf.union(4, 5)
    uf.union(0, 5)
    assert uf.num_sets == 1
    assert {uf.size(x) for x in range(6)} == {6}


def test_redundant_union_changes_nothing():
    uf = UnionFind(range(4))
    uf.union(0, 1)
    uf.union(1, 2)
    before = (uf.groups(), uf.num_sets, [uf.find(x) for x in range(4)])
    assert uf.union(2, 0) is False
    assert (uf.groups(), uf.num_sets, [uf.find(x) for x in range(4)]) == before


def test_len_counts_elements_not_sets():
    uf = UnionFind(range(5))
    uf.union(0, 1)
    uf.union(1, 2)
    assert len(uf) == 5
    assert uf.num_sets == 3


def test_all_members_share_one_representative_that_is_a_member():
    uf = UnionFind(range(8))
    for a, b in [(0, 1), (2, 3), (1, 2), (4, 5), (6, 7), (5, 6)]:
        uf.union(a, b)
    first = {uf.find(x) for x in range(4)}
    second = {uf.find(x) for x in range(4, 8)}
    assert len(first) == 1 and first <= {0, 1, 2, 3}
    assert len(second) == 1 and second <= {4, 5, 6, 7}
    assert first != second
