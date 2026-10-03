from unionfind import UnionFind


def test_new_structure_is_empty():
    uf = UnionFind()
    assert len(uf) == 0
    assert uf.num_sets == 0
    assert uf.groups() == []
    assert "a" not in uf


def test_constructor_adds_each_element_alone_and_ignores_repeats():
    uf = UnionFind(["a", "b", "a", "c", "b"])
    assert len(uf) == 3
    assert uf.num_sets == 3
    assert all(x in uf for x in "abc")
    assert "d" not in uf
    assert all(uf.size(x) == 1 for x in "abc")
    assert not uf.connected("a", "b")


def test_constructor_accepts_any_iterable():
    uf = UnionFind(n * n for n in range(4))
    assert len(uf) == 4
    assert 9 in uf and 4 in uf and 5 not in uf


def test_add_returns_true_for_new_and_false_for_known_elements():
    uf = UnionFind()
    assert uf.add("x") is True
    assert uf.add("x") is False
    assert uf.add("y") is True
    assert len(uf) == 2
    assert uf.num_sets == 2


def test_adding_a_known_element_does_not_split_its_set():
    uf = UnionFind([1, 2, 3])
    uf.union(1, 2)
    assert uf.add(1) is False
    assert uf.add(2) is False
    assert uf.connected(1, 2)
    assert uf.size(2) == 2
    assert uf.num_sets == 2


def test_an_element_alone_is_its_own_representative():
    uf = UnionFind(["p", "q"])
    assert uf.find("p") == "p"
    assert uf.find("q") == "q"
    uf.add("r")
    assert uf.find("r") == "r"


def test_tuples_strings_and_numbers_as_elements():
    uf = UnionFind([(0, 0), (0, 1), "s", 7, 7.5, None])
    assert len(uf) == 6
    assert uf.union((0, 0), (0, 1)) is True
    assert uf.union(None, "s") is True
    assert uf.connected((0, 1), (0, 0))
    assert not uf.connected(7, 7.5)
    assert uf.num_sets == 4
