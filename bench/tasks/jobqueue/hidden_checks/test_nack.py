import pytest
from jobqueue import JobQueue


def make(**kw):
    q = JobQueue(visibility_timeout=10, **kw)
    q.put("a", 1)
    q.put("b", 2)
    return q


def test_nack_gives_the_job_back_at_once():
    q = make()
    q.take(0)
    assert q.nack("a", 1) is None
    assert q.status("a", 1) == "queued"
    assert q.counts(1) == {"queued": 2, "in_flight": 0, "done": 0, "dead": 0}
    assert q.take(1) == ("a", 1)


def test_nack_does_not_wait_for_the_timeout():
    q = make()
    q.take(0)
    q.nack("a", 0.5)
    assert q.take(0.5) == ("a", 1)


def test_nack_errors_for_jobs_that_are_not_in_flight():
    q = make()
    with pytest.raises(KeyError):
        q.nack("ghost", 0)
    with pytest.raises(KeyError):
        q.nack("a", 0)
    q.take(0)
    q.ack("a", 1)
    with pytest.raises(KeyError):
        q.nack("a", 2)
    assert q.status("a", 2) == "done"


def test_nack_after_the_timeout_is_too_late():
    q = make()
    q.take(0)
    with pytest.raises(KeyError):
        q.nack("a", 10)
    assert q.status("a", 10) == "queued"


def test_nack_twice_in_a_row_raises():
    q = make()
    q.take(0)
    q.nack("a", 1)
    with pytest.raises(KeyError):
        q.nack("a", 1)


def test_nack_on_the_last_attempt_kills_the_job():
    q = make(max_attempts=1)
    q.take(0)
    q.nack("a", 1)
    assert q.status("a", 1) == "dead"
    assert q.dead(1) == ["a"]
    assert q.take(1) == ("b", 2)
