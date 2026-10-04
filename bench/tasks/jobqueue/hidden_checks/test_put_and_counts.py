import pytest
from jobqueue import JobQueue


def test_a_new_job_is_queued():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    assert q.status("a", 0) == "queued"
    assert q.counts(0) == {"queued": 1, "in_flight": 0, "done": 0, "dead": 0}


def test_an_empty_queue_has_all_four_counts_at_zero():
    assert JobQueue(visibility_timeout=10).counts(0) == {
        "queued": 0,
        "in_flight": 0,
        "done": 0,
        "dead": 0,
    }


def test_a_known_id_cannot_be_put_again_in_any_state():
    q = JobQueue(visibility_timeout=10, max_attempts=1)
    for name in "abcd":
        q.put(name, 0)
    for _ in range(4):
        q.take(0)
    q.ack("c", 1)
    q.nack("d", 1)
    q.put("e", 0)
    assert q.counts(1) == {"queued": 1, "in_flight": 2, "done": 1, "dead": 1}
    for name in "abcde":
        with pytest.raises(ValueError):
            q.put(name, 99)
    assert q.counts(1) == {"queued": 1, "in_flight": 2, "done": 1, "dead": 1}


def test_a_refused_put_changes_nothing():
    q = JobQueue(visibility_timeout=10)
    q.put("a", "first", priority=1)
    with pytest.raises(ValueError):
        q.put("a", "second", priority=9)
    assert q.counts(0)["queued"] == 1
    assert q.take(0) == ("a", "first")


def test_status_of_an_unknown_job_raises_key_error():
    q = JobQueue(visibility_timeout=10)
    with pytest.raises(KeyError):
        q.status("ghost", 0)


def test_counts_returns_a_new_dict():
    q = JobQueue(visibility_timeout=10)
    q.put("a", 1)
    counts = q.counts(0)
    counts["queued"] = 99
    assert q.counts(0)["queued"] == 1


@pytest.mark.parametrize("timeout", [0, 0.0, -1, -0.5])
def test_non_positive_timeout_raises(timeout):
    with pytest.raises(ValueError):
        JobQueue(visibility_timeout=timeout)


@pytest.mark.parametrize("attempts", [0, -1, 1.5, "3", None])
def test_bad_max_attempts_raises(attempts):
    with pytest.raises(ValueError):
        JobQueue(visibility_timeout=10, max_attempts=attempts)


@pytest.mark.parametrize("job_id", ["", None, 7, b"a"])
def test_bad_job_id_raises(job_id):
    with pytest.raises(ValueError):
        JobQueue(visibility_timeout=10).put(job_id, 1)


@pytest.mark.parametrize("priority", [1.5, "1", None])
def test_bad_priority_raises(priority):
    q = JobQueue(visibility_timeout=10)
    with pytest.raises(ValueError):
        q.put("a", 1, priority=priority)
    assert q.counts(0)["queued"] == 0
