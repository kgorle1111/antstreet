from minheap import MinHeap


class NoCompare:
    def __init__(self, tag):
        self.tag = tag

    def __lt__(self, other):
        raise AssertionError("items must never be compared with each other")

    __gt__ = __le__ = __ge__ = __lt__


def test_dicts_with_a_key_function():
    heap = MinHeap(key=lambda d: d["cost"])
    heap.push({"cost": 3})
    heap.push({"cost": 1})
    heap.push({"cost": 1})
    heap.push({"cost": 2})
    assert [heap.pop()["cost"] for _ in range(4)] == [1, 1, 2, 3]


def test_items_are_never_compared_even_on_ties():
    heap = MinHeap(key=lambda x: x.tag)
    objs = [NoCompare(1), NoCompare(0), NoCompare(1), NoCompare(0), NoCompare(1)]
    for obj in objs:
        heap.push(obj)
    popped = [heap.pop() for _ in range(5)]
    assert popped == [objs[1], objs[3], objs[0], objs[2], objs[4]]


def test_replace_and_items_do_not_compare_items_either():
    heap = MinHeap(key=lambda x: x.tag)
    objs = [NoCompare(1) for _ in range(4)]
    for obj in objs[:3]:
        heap.push(obj)
    assert heap.replace(objs[3]) is objs[0]
    assert heap.items() == [objs[1], objs[2], objs[3]]
    assert heap.peek() is objs[1]


def test_none_and_falsy_items_are_ordinary_items():
    heap = MinHeap(key=lambda x: 0 if x is None else 1)
    heap.push("x")
    heap.push(None)
    heap.push("")
    assert heap.pop() is None
    assert heap.pop() == "x"
    assert heap.pop() == ""
