"""Append-only JSONL ledger: the single source of truth for every cent and decision in a run."""

from __future__ import annotations

import fcntl
import json
import os
import re
from collections.abc import Callable, Hashable, Iterable
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

LEDGER_VERSION = 1
_ACTOR_RE = re.compile(r"^(boss|gate|rule|investor|worker:[A-Za-z0-9_-]+)$")


class EventType(StrEnum):
    BOSS_CALL = "boss_call"  # the boss's own model spend, e.g. drafting the term sheet
    HIRED = "hired"
    SLICE_START = "slice_start"
    SLICE_END = "slice_end"
    CHECK_RESULT = "check_result"
    BLOCKED = "blocked"
    DISPUTED = "disputed"  # a worker says a check contradicts the idea; the investor rules on it
    FIRED = "fired"
    ABANDONED = "abandoned"  # a task nobody will work on further in this run
    REASSIGNED = "reassigned"
    ROUND_CLOSED = "round_closed"
    APPROVED = "approved"
    TOPPED_UP = "topped_up"
    PAUSED = "paused"
    STOPPED = "stopped"
    DENIED = "denied"
    ERROR = "error"


class Billing(StrEnum):
    API = "api"
    SUBSCRIPTION = "subscription"
    UNKNOWN = "unknown"


class LedgerError(Exception):
    """Base class for ledger failures."""


class LedgerCorruptError(LedgerError):
    """A line in the ledger file is not a valid event."""


class LedgerLockedError(LedgerError):
    """Another writer already holds the ledger."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_count(name: str, value: object) -> None:
    # bool is a subclass of int; a True token count is a bug, not 1.
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative int, got {value!r}")


@dataclass(frozen=True, slots=True)
class Event:
    """One ledger line.

    `cost_micros` is the estimated cost in millionths of a US dollar (whole cents are too coarse:
    a boss call costs about $0.004). `None` means unknown, which is never the same as 0.
    """

    run: str
    round: int
    actor: str
    event: EventType
    cost_micros: int | None = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    billing: Billing = Billing.UNKNOWN
    data: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        for name in ("run", "actor", "ts"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string, got {getattr(self, name)!r}")
        if not self.run:
            raise ValueError("run must be non-empty")
        _require_count("round", self.round)
        if not _ACTOR_RE.fullmatch(self.actor):  # match() would let "boss\n" through `$`
            raise ValueError(f"unknown actor {self.actor!r}")
        datetime.fromisoformat(self.ts)  # raises ValueError on anything else
        object.__setattr__(self, "event", EventType(self.event))
        object.__setattr__(self, "billing", Billing(self.billing))
        if self.cost_micros is not None:
            _require_count("cost_micros", self.cost_micros)
        for name in ("tokens_in", "tokens_out", "tokens_cached"):
            _require_count(name, getattr(self, name))
        if not isinstance(self.data, dict):
            raise ValueError("data must be a dict")

    def to_json(self) -> str:
        return json.dumps({"v": LEDGER_VERSION, **asdict(self)}, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> Event:
        try:
            raw = json.loads(line)
        except RecursionError:  # a deeply nested line is corrupt, not a crash
            raise ValueError("line nested too deeply") from None
        if not isinstance(raw, dict) or raw.pop("v", None) != LEDGER_VERSION:
            raise ValueError(f"not a v{LEDGER_VERSION} ledger event")
        expected = {f.name for f in fields(cls)}
        if set(raw) != expected:
            raise ValueError(f"fields differ from schema: {sorted(set(raw) ^ expected)}")
        return cls(**raw)


class LedgerWriter:
    """Exclusive appender. Use as a context manager; a second writer on the same file is refused."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fh: IO[str] | None = None

    def __enter__(self) -> LedgerWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise LedgerLockedError(f"{self.path} is held by another writer") from None
        self._fh = fh
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None

    def append(self, event: Event) -> None:
        if self._fh is None:
            raise LedgerError("writer is not open; use `with LedgerWriter(path) as w:`")
        line = event.to_json()  # serialise first so a bad event never leaves a partial line
        self._fh.write(line + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())  # money records must survive a crash right after append


def read_events(path: Path) -> list[Event]:
    """Parse every line; any invalid line raises with its line number."""
    # kn: a torn final line after a hard kill also raises;
    # tolerant tail handling arrives with run resume (plan step 2.15).
    events: list[Event] = []
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            try:
                events.append(Event.from_json(line))
            except (ValueError, TypeError) as exc:
                raise LedgerCorruptError(f"{path}:{lineno}: {exc}") from exc
    return events


@dataclass(frozen=True, slots=True)
class Totals:
    cost_micros: int = 0
    unknown_cost_events: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    events: int = 0


def total(events: Iterable[Event]) -> Totals:
    micros = unknown = t_in = t_out = t_cached = count = 0
    for e in events:
        count += 1
        if e.cost_micros is None:
            unknown += 1
        else:
            micros += e.cost_micros
        t_in += e.tokens_in
        t_out += e.tokens_out
        t_cached += e.tokens_cached
    return Totals(micros, unknown, t_in, t_out, t_cached, count)


def totals_by[K: Hashable](events: Iterable[Event], key: Callable[[Event], K]) -> dict[K, Totals]:
    groups: dict[K, list[Event]] = {}
    for e in events:
        groups.setdefault(key(e), []).append(e)
    return {k: total(v) for k, v in groups.items()}
