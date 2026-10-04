from jobqueue import JobQueue


def test_a_nacked_job_goes_ahead_of_jobs_put_after_it():
    q = JobQueue(visibility_timeout=10)
    for name in "abc":
        q.put(name, name)
    assert q.take(0)[0] == "a"
    q.nack("a", 1)
    assert q.take(2)[0] == "a"
    assert q.take(2)[0] == "b"


def test_an_expired_job_goes_ahead_of_jobs_put_after_it():
    q = JobQueue(visibility_timeout=10)
    for name in "abc":
        q.put(name, name)
    assert q.take(0)[0] == "a"
    assert q.take(1)[0] == "b"
    assert q.take(10.5)[0] == "a"
    assert q.take(10.5)[0] == "c"
    assert q.take(11)[0] == "b"


def test_a_job_taken_twice_returns_to_its_original_place_each_time():
    q = JobQueue(visibility_timeout=10, max_attempts=5)
    q.put("a", 1)
    q.put("b", 2)
    for now in (0, 2, 4):
        assert q.take(now)[0] == "a"
        q.nack("a", now)
    assert q.take(5)[0] == "a"


def test_a_requeued_job_keeps_its_priority():
    q = JobQueue(visibility_timeout=10)
    q.put("low", 1, priority=0)
    q.put("high", 2, priority=5)
    q.put("mid", 3, priority=2)
    assert q.take(0)[0] == "high"
    q.nack("high", 1)
    assert q.take(2)[0] == "high"
    assert q.take(2)[0] == "mid"
    assert q.take(2)[0] == "low"


def test_requeued_jobs_are_ordered_by_priority_then_put_order_with_the_rest():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 0)
    q.put("b", 0)
    q.put("c", 0, priority=3)
    assert q.take(0)[0] == "c"
    assert q.take(0)[0] == "a"
    q.nack("a", 1)
    q.put("d", 0, priority=3)
    assert q.take(2)[0] == "d"
    assert q.take(2)[0] == "a"
    assert q.take(2)[0] == "b"
