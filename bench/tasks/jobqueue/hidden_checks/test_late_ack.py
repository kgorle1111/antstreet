import pytest
from jobqueue import JobQueue


def test_ack_just_before_the_timeout_succeeds():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(0)
    q.ack("a", 9.9)
    assert q.status("a", 100) == "done"


def test_ack_at_exactly_the_timeout_is_too_late():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(0)
    with pytest.raises(KeyError):
        q.ack("a", 10)
    assert q.status("a", 10) == "queued"
    assert q.take(10) == ("a", 1)


def test_ack_after_the_job_was_handed_to_another_worker_is_for_the_new_worker():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.take(0)
    assert q.take(10) == ("a", 1)
    q.ack("a", 12)
    assert q.status("a", 12) == "done"


def test_ack_after_the_job_died_of_expiry_raises():
    q = JobQueue(visibility_timeout=10, max_attempts=1)
    q.put("a", 1)
    q.take(0)
    with pytest.raises(KeyError):
        q.ack("a", 50)
    assert q.status("a", 50) == "dead"
    assert q.dead(50) == ["a"]


def test_a_late_ack_for_one_job_does_not_disturb_the_others():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.put("b", 2)
    q.take(0)
    q.take(8)
    with pytest.raises(KeyError):
        q.ack("a", 12)
    q.ack("b", 12)
    assert q.counts(12) == {"queued": 1, "in_flight": 0, "done": 1, "dead": 0}
