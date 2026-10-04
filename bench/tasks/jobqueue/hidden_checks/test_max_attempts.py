from jobqueue import JobQueue


def test_a_job_that_keeps_expiring_dies_after_max_attempts_takes():
    q = JobQueue(visibility_timeout=10, max_attempts=2)
    q.put("a", 1)
    assert q.take(0) == ("a", 1)
    assert q.status("a", 10) == "queued"
    assert q.take(10) == ("a", 1)
    assert q.status("a", 19.9) == "in_flight"
    assert q.status("a", 20) == "dead"
    assert q.dead(20) == ["a"]
    assert q.take(20) is None
    assert q.counts(20) == {"queued": 0, "in_flight": 0, "done": 0, "dead": 1}


def test_nacks_count_as_attempts_too():
    q = JobQueue(visibility_timeout=10, max_attempts=2)
    q.put("a", 1)
    q.take(0)
    q.nack("a", 1)
    assert q.status("a", 1) == "queued"
    q.take(2)
    q.nack("a", 3)
    assert q.status("a", 3) == "dead"


def test_default_is_three_attempts():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    for now in (0, 1):
        q.take(now)
        q.nack("a", now)
        assert q.status("a", now) == "queued"
    q.take(2)
    q.nack("a", 2)
    assert q.status("a", 2) == "dead"


def test_one_attempt_means_no_second_chance():
    q = JobQueue(visibility_timeout=10, max_attempts=1)
    q.put("a", 1)
    q.take(0)
    assert q.status("a", 10) == "dead"


def test_a_job_acknowledged_on_its_last_attempt_is_done_not_dead():
    q = JobQueue(visibility_timeout=10, max_attempts=2)
    q.put("a", 1)
    q.take(0)
    q.nack("a", 1)
    q.take(2)
    q.ack("a", 3)
    assert q.status("a", 3) == "done"
    assert q.dead(100) == []


def test_dead_jobs_are_listed_in_the_order_they_died():
    q = JobQueue(visibility_timeout=10, max_attempts=1)
    q.put("a", 0, priority=0)
    q.put("b", 0, priority=1)
    q.put("c", 0, priority=2)
    q.put("d", 0, priority=3)
    assert [q.take(now)[0] for now in (0, 1, 2, 3)] == ["d", "c", "b", "a"]
    q.nack("c", 4)
    assert q.dead(4) == ["c"]
    assert q.dead(20) == ["c", "d", "b", "a"]


def test_dead_returns_a_new_list_and_a_dead_job_is_not_handed_out():
    q = JobQueue(visibility_timeout=10, max_attempts=1)
    q.put("a", 1)
    q.take(0)
    got = q.dead(10)
    got.append("zzz")
    assert q.dead(10) == ["a"]
    assert q.take(11) is None


def test_attempts_are_per_job():
    q = JobQueue(visibility_timeout=10, max_attempts=2)
    q.put("a", 1)
    q.put("b", 2)
    q.take(0)
    q.nack("a", 1)
    q.take(2)
    q.take(3)
    q.nack("b", 4)
    assert q.status("a", 4) == "in_flight"
    assert q.status("b", 4) == "queued"
