import pytest
from unionfind import UnionFind


def test_find_size_and_connected_raise_key_error_for_unknown_elements():
    uf = UnionFind(["a", "b"])
    with pytest.raises(KeyError):
        uf.find("zzz")
    with pytest.raises(KeyError):
        uf.size("zzz")
    with pytest.raises(KeyError):
        uf.connected("a", "zzz")
    with pytest.raises(KeyError):
        uf.connected("zzz", "a")
    with pytest.raises(KeyError):
        uf.connected("y", "zzz")


def test_union_with_an_unknown_element_raises_key_error():
    uf = UnionFind(["a", "b"])
    with pytest.raises(KeyError):
        uf.union("a", "zzz")
    with pytest.raises(KeyError):
        uf.union("zzz", "a")


def test_failed_union_does_not_add_the_unknown_element():
    uf = UnionFind(["a", "b"])
    with pytest.raises(KeyError):
        uf.union("a", "new")
    assert "new" not in uf
    assert len(uf) == 2
    assert uf.num_sets == 2


def test_failed_union_does_not_add_the_known_element_when_the_first_is_unknown():
    uf = UnionFind(["a"])
    with pytest.raises(KeyError):
        uf.union("new", "a")
    assert "new" not in uf
    assert uf.groups() == [["a"]]


def test_failed_union_with_two_unknown_elements_adds_neither():
    uf = UnionFind(["a"])
    with pytest.raises(KeyError):
        uf.union("x", "y")
    assert len(uf) == 1
    assert "x" not in uf and "y" not in uf


def test_failed_union_leaves_existing_sets_untouched():
    uf = UnionFind([1, 2, 3])
    uf.union(1, 2)
    with pytest.raises(KeyError):
        uf.union(2, 99)
    assert uf.groups() == [[1, 2], [3]]
    assert uf.size(1) == 2
    assert uf.find(2) == 1


def test_an_unknown_element_can_be_added_after_the_error():
    uf = UnionFind(["a"])
    with pytest.raises(KeyError):
        uf.find("b")
    assert uf.add("b") is True
    assert uf.find("b") == "b"
    assert uf.union("a", "b") is True


def test_empty_structure_raises_for_everything():
    uf = UnionFind()
    with pytest.raises(KeyError):
        uf.find(0)
    with pytest.raises(KeyError):
        uf.union(0, 1)
