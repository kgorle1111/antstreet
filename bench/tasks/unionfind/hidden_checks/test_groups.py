from unionfind import UnionFind


def test_groups_follow_insertion_order_not_sorted_order():
    uf = UnionFind([3, 1, 2])
    uf.union(1, 3)
    assert uf.groups() == [[3, 1], [2]]


def test_sets_are_ordered_by_their_earliest_added_element():
    uf = UnionFind(["d", "a", "c", "b", "e"])
    uf.union("b", "d")
    uf.union("e", "a")
    assert uf.groups() == [["d", "b"], ["a", "e"], ["c"]]


def test_order_inside_a_group_does_not_depend_on_union_order():
    uf = UnionFind([5, 4, 3, 2, 1])
    uf.union(1, 5)
    uf.union(3, 1)
    uf.union(2, 5)
    assert uf.groups() == [[5, 3, 2, 1], [4]]


def test_each_element_alone_gives_singleton_groups_in_order():
    assert UnionFind([2, 9, 4]).groups() == [[2], [9], [4]]


def test_everything_joined_gives_one_group_in_insertion_order():
    uf = UnionFind([4, 2, 3, 1])
    for n in [1, 3, 2, 4]:
        uf.union(4, n)
    assert uf.groups() == [[4, 2, 3, 1]]


def test_elements_added_later_come_after_in_their_own_groups():
    uf = UnionFind(["a", "b"])
    uf.union("a", "b")
    uf.add("z")
    uf.add("c")
    uf.union("c", "a")
    assert uf.groups() == [["a", "b", "c"], ["z"]]


def test_groups_returns_new_lists_each_call():
    uf = UnionFind([1, 2, 3])
    uf.union(1, 2)
    result = uf.groups()
    result[0].append(99)
    result.clear()
    assert uf.groups() == [[1, 2], [3]]
    assert len(uf) == 3
