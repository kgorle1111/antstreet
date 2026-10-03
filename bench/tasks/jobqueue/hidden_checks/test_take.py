from jobqueue import JobQueue


def test_take_on_an_empty_queue_is_none():
    assert JobQueue(visibility_timeout=10).take(0) is None


def test_take_when_everything_is_in_flight_is_none():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.put("b", 2)
    assert q.take(0) is not None
    assert q.take(1) is not None
    assert q.take(2) is None
    assert q.take(9.5) is None


def test_none_is_a_payload_like_any_other():
    q = JobQueue(visibility_timeout=10)
    q.put("a", None)
    assert q.take(0) == ("a", None)


def test_a_taken_job_is_in_flight_and_counted():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.put("b", 2)
    assert q.status("a", 0) == "queued"
    q.take(0)
    assert q.status("a", 1) == "in_flight"
    assert q.status("b", 1) == "queued"
    assert q.counts(1) == {"queued": 1, "in_flight": 1, "done": 0, "dead": 0}


def test_one_job_is_never_handed_to_two_workers():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    first = q.take(0)
    second = q.take(5)
    assert first == ("a", 1)
    assert second is None


def test_put_does_not_disturb_jobs_in_flight():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(0)
    q.put("b", 2)
    assert q.status("a", 1) == "in_flight"
    assert q.take(1) == ("b", 2)
