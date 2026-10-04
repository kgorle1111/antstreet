import pytest
from jobqueue import JobQueue


def test_job_is_invisible_until_the_timeout_then_handed_out_again():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(100)
    assert q.take(109.9) is None
    assert q.status("a", 109.9) == "in_flight"
    assert q.take(110) == ("a", 1)


def test_exactly_the_timeout_is_enough_to_expire():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(100)
    assert q.status("a", 110) == "queued"
    assert q.counts(110) == {"queued": 1, "in_flight": 0, "done": 0, "dead": 0}


def test_expiry_is_noticed_by_counts_and_status_without_any_take():
    q = JobQueue(visibility_timeout=5)
    q.put("a", 1)
    q.put("b", 2)
    q.take(0)
    q.take(2)
    assert q.counts(4.9) == {"queued": 0, "in_flight": 2, "done": 0, "dead": 0}
    assert q.counts(5) == {"queued": 1, "in_flight": 1, "done": 0, "dead": 0}
    assert q.counts(7) == {"queued": 2, "in_flight": 0, "done": 0, "dead": 0}


def test_each_take_restarts_the_clock_for_that_job():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(0)
    assert q.take(10) == ("a", 1)
    assert q.status("a", 19.9) == "in_flight"
    assert q.status("a", 20) == "queued"


def test_fractional_timeout():
    q = JobQueue(visibility_timeout=0.5)
    q.put("a", 1)
    q.take(1.0)
    assert q.status("a", 1.25) == "in_flight"
    assert q.status("a", 1.5) == "queued"


def test_jobs_expire_independently():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.put("b", 2)
    q.take(0)
    q.take(6)
    assert q.status("a", 12) == "queued"
    assert q.status("b", 12) == "in_flight"
    assert q.status("b", 16) == "queued"


def test_a_late_ack_fails_because_the_job_expired():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(0)
    with pytest.raises(KeyError):
        q.ack("a", 10)
    assert q.status("a", 10) == "queued"
