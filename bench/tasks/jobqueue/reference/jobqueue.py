from dataclasses import dataclass
from typing import Any

STATES = ("queued", "in_flight", "done", "dead")


@dataclass(slots=True)
class _Job:
    job_id: str
    payload: Any
    priority: int
    put_no: int
    state: str = "queued"
    attempts: int = 0
    taken_at: float = 0.0
    taken_no: int = 0


class JobQueue:
    def __init__(self, visibility_timeout: float, max_attempts: int = 3) -> None:
        if visibility_timeout <= 0:
            raise ValueError("visibility_timeout must be positive")
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a whole number of at least 1")
        self._timeout = visibility_timeout
        self._max_attempts = max_attempts
        self._jobs: dict[str, _Job] = {}
        self._dead: list[str] = []
        self._takes = 0

    def put(self, job_id: str, payload: Any, priority: int = 0) -> None:
        if type(job_id) is not str or not job_id:
            raise ValueError("job_id must be a non-empty string")
        if type(priority) is not int:
            raise ValueError("priority must be a whole number")
        if job_id in self._jobs:
            raise ValueError(f"job {job_id!r} is already known")
        self._jobs[job_id] = _Job(job_id, payload, priority, put_no=len(self._jobs))

    def _release(self, job: _Job) -> None:
        if job.attempts >= self._max_attempts:
            job.state = "dead"
            self._dead.append(job.job_id)
        else:
            job.state = "queued"

    def _expire(self, now: float) -> None:
        late = [j for j in self._jobs.values() if j.state == "in_flight"]
        late = [j for j in late if now - j.taken_at >= self._timeout]
        for job in sorted(late, key=lambda j: j.taken_no):
            self._release(job)

    def take(self, now: float) -> tuple[str, Any] | None:
        self._expire(now)
        queued = [j for j in self._jobs.values() if j.state == "queued"]
        if not queued:
            return None
        job = min(queued, key=lambda j: (-j.priority, j.put_no))
        self._takes += 1
        job.state = "in_flight"
        job.attempts += 1
        job.taken_at = now
        job.taken_no = self._takes
        return job.job_id, job.payload

    def _in_flight(self, job_id: str, now: float) -> _Job:
        self._expire(now)
        job = self._jobs.get(job_id)
        if job is None or job.state != "in_flight":
            raise KeyError(job_id)
        return job

    def ack(self, job_id: str, now: float) -> None:
        self._in_flight(job_id, now).state = "done"

    def nack(self, job_id: str, now: float) -> None:
        self._release(self._in_flight(job_id, now))

    def status(self, job_id: str, now: float) -> str:
        self._expire(now)
        return self._jobs[job_id].state

    def counts(self, now: float) -> dict[str, int]:
        self._expire(now)
        counts = dict.fromkeys(STATES, 0)
        for job in self._jobs.values():
            counts[job.state] += 1
        return counts

    def dead(self, now: float) -> list[str]:
        self._expire(now)
        return list(self._dead)
