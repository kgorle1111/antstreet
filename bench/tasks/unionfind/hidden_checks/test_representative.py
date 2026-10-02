from unionfind import UnionFind


def test_equal_sizes_keep_the_first_arguments_representative():
    uf = UnionFind([1, 2, 3, 4])
    uf.union(1, 2)
    assert uf.find(1) == uf.find(2) == 1
    uf.union(4, 3)
    assert uf.find(3) == uf.find(4) == 4


def test_a_tie_between_bigger_sets_also_goes_to_the_first_argument():
    uf = UnionFind([1, 2, 3, 4])
    uf.union(1, 2)
    uf.union(3, 4)
    uf.union(3, 1)
    assert {uf.find(x) for x in (1, 2, 3, 4)} == {3}

    uf = UnionFind([1, 2, 3, 4])
    uf.union(1, 2)
    uf.union(3, 4)
    uf.union(1, 3)
    assert {uf.find(x) for x in (1, 2, 3, 4)} == {1}


def test_the_larger_set_keeps_its_representative_whichever_side_it_is_on():
    uf = UnionFind([1, 2, 3, 4, 5])
    uf.union(1, 2)
    uf.union(1, 3)
    assert uf.find(3) == 1
    assert uf.union(5, 1) is True
    assert {uf.find(x) for x in (1, 2, 3, 5)} == {1}

    uf = UnionFind([1, 2, 3, 4, 5])
    uf.union(1, 2)
    uf.union(1, 3)
    uf.union(1, 5)
    assert {uf.find(x) for x in (1, 2, 3, 5)} == {1}


def test_smaller_first_argument_loses_to_a_larger_second_set():
    uf = UnionFind(["a", "b", "c", "d", "e"])
    uf.union("b", "c")
    uf.union("b", "d")
    assert uf.find("d") == "b"
    uf.union("e", "d")
    assert {uf.find(x) for x in "bcde"} == {"b"}
    assert uf.find("a") == "a"


def test_two_sets_of_different_size_with_a_big_second_set():
    uf = UnionFind(range(10))
    for n in range(5, 9):
        uf.union(5, n)
    uf.union(0, 1)
    assert uf.size(5) == 4 and uf.size(0) == 2
    uf.union(0, 5)
    assert {uf.find(x) for x in (0, 1, 5, 6, 7, 8)} == {5}


def test_find_never_changes_a_representative():
    uf = UnionFind(range(12))
    for n in range(1, 12):
        uf.union(n - 1, n)
    reps = [uf.find(x) for x in range(12)]
    for _ in range(3):
        assert [uf.find(x) for x in range(12)] == reps
    assert len(set(reps)) == 1


def test_representative_is_stable_across_redundant_unions():
    uf = UnionFind([1, 2, 3])
    uf.union(2, 1)
    rep = uf.find(1)
    assert rep == 2
    assert uf.union(1, 2) is False
    assert uf.union(2, 1) is False
    assert uf.find(1) == uf.find(2) == rep
