from minheap import MinHeap


def drain(heap):
    out = []
    while heap:
        out.append(heap.pop())
    return out


def test_equal_priorities_come_out_first_in_first_out():
    heap = MinHeap(key=lambda d: d["p"])
    jobs = [{"p": 1, "id": n} for n in range(20)]
    for job in jobs:
        heap.push(job)
    assert [j["id"] for j in drain(heap)] == list(range(20))


def test_ties_inside_mixed_priorities():
    heap = MinHeap(key=lambda d: d["p"])
    for p, name in [(2, "a"), (1, "b"), (2, "c"), (1, "d"), (0, "e"), (2, "f"), (1, "g")]:
        heap.push({"p": p, "id": name})
    assert [j["id"] for j in drain(heap)] == ["e", "b", "d", "g", "a", "c", "f"]


def test_ties_hold_across_interleaved_pops():
    heap = MinHeap(key=lambda t: t[0])
    heap.push((1, "a"))
    heap.push((1, "b"))
    assert heap.pop() == (1, "a")
    heap.push((1, "c"))
    heap.push((0, "d"))
    heap.push((1, "e"))
    assert drain(heap) == [(0, "d"), (1, "b"), (1, "c"), (1, "e")]


def test_same_object_pushed_twice_is_two_entries():
    heap = MinHeap(key=lambda d: d["p"])
    job = {"p": 1}
    heap.push(job)
    heap.push(job)
    assert len(heap) == 2
    assert heap.pop() is job
    assert heap.pop() is job
    assert len(heap) == 0


def test_equal_priority_with_a_less_than_only_priority_type():
    class Prio:
        def __init__(self, n):
            self.n = n

        def __lt__(self, other):
            return self.n < other.n

    heap = MinHeap(key=lambda item: Prio(item[0]))
    for item in [(1, "a"), (1, "b"), (0, "c"), (1, "d")]:
        heap.push(item)
    assert drain(heap) == [(0, "c"), (1, "a"), (1, "b"), (1, "d")]
