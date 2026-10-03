from jobqueue import JobQueue


def drain(q, now=0):
    got = []
    while (item := q.take(now)) is not None:
        got.append(item[0])
    return got


def test_higher_priority_goes_first():
    q = JobQueue(visibility_timeout=10)
    q.put("a", "pa", priority=0)
    q.put("b", "pb", priority=5)
    q.put("c", "pc", priority=1)
    assert drain(q) == ["b", "c", "a"]


def test_equal_priorities_are_first_in_first_out():
    q = JobQueue(visibility_timeout=10)
    for name in "xyz":
        q.put(name, None)
    assert drain(q) == ["x", "y", "z"]


def test_mixed_priorities_keep_put_order_within_a_level():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1, priority=1)
    q.put("b", 2, priority=1)
    q.put("c", 3, priority=2)
    q.put("d", 4, priority=1)
    assert drain(q) == ["c", "a", "b", "d"]


def test_negative_priorities_sort_below_zero():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 0, priority=-1)
    q.put("b", 0, priority=0)
    q.put("c", 0, priority=-5)
    assert drain(q) == ["b", "a", "c"]


def test_a_job_put_later_with_a_higher_priority_jumps_the_queue():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 0)
    q.put("b", 0)
    q.put("urgent", 0, priority=9)
    assert q.take(0)[0] == "urgent"
    assert q.take(0)[0] == "a"


def test_a_job_put_after_a_take_is_ordered_with_the_rest():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 0)
    q.put("b", 0)
    assert q.take(0)[0] == "a"
    q.put("c", 0, priority=1)
    q.put("d", 0)
    assert drain(q) == ["c", "b", "d"]


def test_take_returns_the_id_and_the_payload_as_a_tuple():
    q = JobQueue(visibility_timeout=10)
    payload = {"n": [1, 2]}
    q.put("a", payload)
    got = q.take(0)
    assert isinstance(got, tuple)
    assert got == ("a", {"n": [1, 2]})
    assert got[1] is payload
