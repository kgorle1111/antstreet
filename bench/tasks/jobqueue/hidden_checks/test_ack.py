import pytest
from jobqueue import JobQueue


def make():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    q.put("b", 2)
    return q


def test_ack_marks_the_job_done_and_it_is_not_handed_out_again():
    q = make()
    q.take(0)
    assert q.ack("a", 1) is None
    assert q.status("a", 1) == "done"
    assert q.counts(1) == {"queued": 1, "in_flight": 0, "done": 1, "dead": 0}
    assert q.take(1) == ("b", 2)
    assert q.status("a", 1000) == "done"


def test_done_jobs_stay_done_after_the_timeout():
    q = make()
    q.take(0)
    q.ack("a", 5)
    assert q.status("a", 100) == "done"


def test_jobs_may_be_acknowledged_in_any_order():
    q = make()
    q.take(0)
    q.take(1)
    q.ack("b", 2)
    q.ack("a", 3)
    assert q.counts(3) == {"queued": 0, "in_flight": 0, "done": 2, "dead": 0}


def test_ack_of_an_unknown_job_raises_key_error():
    q = make()
    with pytest.raises(KeyError):
        q.ack("ghost", 0)


def test_ack_of_a_job_that_was_never_taken_raises_key_error():
    q = make()
    with pytest.raises(KeyError):
        q.ack("a", 0)
    assert q.status("a", 0) == "queued"


def test_ack_twice_raises_key_error():
    q = make()
    q.take(0)
    q.ack("a", 1)
    with pytest.raises(KeyError):
        q.ack("a", 2)
    assert q.status("a", 2) == "done"


def test_ack_of_a_dead_job_raises_key_error():
    q = JobQueue(visibility_timeout=10, max_attempts=1)
    q.put("a", 1)
    q.take(0)
    q.nack("a", 1)
    with pytest.raises(KeyError):
        q.ack("a", 2)
    assert q.status("a", 2) == "dead"
