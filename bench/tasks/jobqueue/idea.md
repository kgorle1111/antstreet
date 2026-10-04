Create a Python module `jobqueue.py` (standard library only) with one class:

    JobQueue(visibility_timeout: float, max_attempts: int = 3)

    put(job_id: str, payload, priority: int = 0) -> None
    take(now: float) -> tuple[str, object] | None
    ack(job_id: str, now: float) -> None
    nack(job_id: str, now: float) -> None
    status(job_id: str, now: float) -> str
    counts(now: float) -> dict[str, int]
    dead(now: float) -> list[str]

It is a work queue in the style of a cloud message queue. A worker takes a job, and the job stays
invisible to other workers until the worker acknowledges it, gives it back, or runs out of time.
The queue never reads a clock: `now` is the time in seconds given by the caller, and does not go
backwards between calls. `payload` is any object, `None` included.

1. `visibility_timeout` must be greater than 0 and `max_attempts` a whole number of at least 1;
   otherwise the constructor raises `ValueError`.
2. Every job is in exactly one state: `"queued"`, `"in_flight"`, `"done"` or `"dead"`.
   `put(job_id, payload, priority=0)` adds a new job in the state `"queued"`. `job_id` must be a
   non-empty `str` and `priority` a whole number (larger means more urgent, negative is allowed),
   otherwise `ValueError`. A `job_id` the queue already knows, in any state, raises `ValueError`
   and changes nothing. `put` takes no `now`. The order of the `put` calls decides the put order
   of the jobs.
3. `take(now)` hands out the queued job with the highest priority; among equal priorities the one
   that was put first. It returns `(job_id, payload)`, moves the job to `"in_flight"`, records
   `now` as the time it was taken, and counts one more attempt for it. With no queued job it
   returns `None`. A job that is being returned to the queue (see 4 and 6) keeps its priority and its
   original put order, so it goes ahead of jobs that were put after it.
4. A job taken at time `t` expires once `now - t >= visibility_timeout` (exactly the timeout is
   enough). Every method that takes `now` first deals with all jobs that have expired by that
   `now`, before anything else it does. An expired job that has been taken `max_attempts` times
   becomes `"dead"`; any other expired job goes back to `"queued"`. Several jobs that expire in
   the same call are dealt with in the order they were taken.
5. `ack(job_id, now)` moves an in-flight job to `"done"`. A job that is not in flight at that
   moment (unknown, queued, done, dead, or expired just now, see 4) raises `KeyError` and changes
   nothing.
6. `nack(job_id, now)` gives an in-flight job back at once: it becomes `"dead"` if it has already
   been taken `max_attempts` times, otherwise `"queued"`. The same `KeyError` rule as `ack`.
7. `status(job_id, now)` returns the job's state, or raises `KeyError` for an unknown id.
   `counts(now)` returns a new dict with the four states as keys and the number of jobs in each
   as values (0 included). `dead(now)` returns a new list of the ids of the dead jobs, in the order
   they became dead.
