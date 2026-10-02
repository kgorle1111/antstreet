"""Append-only JSONL ledger: the single source of truth for every cent and decision in a run."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Hashable, Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

LEDGER_VERSION = 1
# `prev` of the first line of a chained ledger. Fixed, so a deleted first line is detected too.
GENESIS = "0" * 64
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
_ACTOR_RE = re.compile(r"^(boss|gate|rule|investor|worker:[A-Za-z0-9_-]+|role:[a-z][a-z_]*)\Z")


class EventType(StrEnum):
    BOSS_CALL = "boss_call"  # the boss's own model spend, e.g. drafting the term sheet
    ROLE_CALL = "role_call"  # a specialist role's model spend (actor `role:<name>`)
    STARTED = "started"  # the configuration a run was started with, so it can be resumed
    RESUMED = "resumed"  # the investor lifted an earlier stop; everything is verified again
    HIRED = "hired"
    SLICE_START = "slice_start"
    SLICE_END = "slice_end"
    CHECK_RESULT = "check_result"
    BLOCKED = "blocked"
    RULED = "ruled"  # the investor's ruling on a disputed check or a blocked task
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
    # The chain link, set by `LedgerWriter` and read back by `read_events`; it is a property of
    # the line in its file, so two equal events at different places stay equal.
    prev: str | None = field(default=None, compare=False, repr=False)

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
        if self.prev is not None and not (
            isinstance(self.prev, str) and _HASH_RE.fullmatch(self.prev)
        ):
            raise ValueError(f"prev must be 64 lower-case hex digits, got {self.prev!r}")

    def to_json(self) -> str:
        line = {"v": LEDGER_VERSION, **asdict(self)}
        if line["prev"] is None:  # an unchained event has no `prev` key at all
            del line["prev"]
        return json.dumps(line, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> Event:
        try:
            raw = json.loads(line)
        except RecursionError:  # a deeply nested line is corrupt, not a crash
            raise ValueError("line nested too deeply") from None
        version = raw.pop("v", None) if isinstance(raw, dict) else None
        # exact int: True == 1 and 1.0 == 1 must not pass as a version.
        if type(version) is not int or version != LEDGER_VERSION:
            raise ValueError(f"not a v{LEDGER_VERSION} ledger event")
        expected = {f.name for f in fields(cls)}
        if "prev" not in raw:  # a line from before the chain existed
            raw["prev"] = None
        elif not isinstance(raw["prev"], str):  # `"prev": null` is not a way to opt out
            raise ValueError("prev must be a string")
        if set(raw) != expected:
            raise ValueError(f"fields differ from schema: {sorted(set(raw) ^ expected)}")
        return cls(**raw)


def _sha256(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def _last_line_hash(path: Path) -> str:
    """What the next line's `prev` must be: the hash of the file's last line, without its newline.

    Reads the whole file once per open. A cut-off last line (no newline) is hashed as it is: a
    line appended to it is glued on and the file is corrupt either way, which `read_events`
    reports; `repair_torn_tail` has to run before a writer opens.
    """
    data = Path(path).read_bytes()
    if not data:
        return GENESIS
    return _sha256(data.removesuffix(b"\n").rsplit(b"\n", 1)[-1])


class LedgerWriter:
    """Exclusive appender. Use as a context manager; a second writer on the same file is refused."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fh: IO[str] | None = None
        self._prev = GENESIS
        self._append_lock = threading.Lock()  # parallel slices append from several threads

    def __enter__(self) -> LedgerWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise LedgerLockedError(f"{self.path} is held by another writer") from None
        try:
            self._prev = _last_line_hash(self.path)  # under the lock: nobody appends meanwhile
        except BaseException:
            fcntl.flock(fh, fcntl.LOCK_UN)
            fh.close()
            raise
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
        with self._append_lock:  # the link, the write and the next link are one step
            # serialise first so a bad event never leaves a partial line
            line = replace(event, prev=self._prev).to_json()
            self._fh.write(line + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())  # money records must survive a crash right after append
            self._prev = _sha256(line.encode("utf-8"))


def repair_torn_tail(path: Path) -> str | None:
    """Cut an incomplete final line left by a hard kill and return the removed text.

    Acts only when the file does not end with a newline (`LedgerWriter.append` always writes
    one), every line before the last is a valid event, and the last is not. Anything else is
    left untouched for `read_events` to reject. Takes the writer's lock, so it is refused while
    a writer is open.
    """
    with suppress(FileNotFoundError), Path(path).open("r+b") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LedgerLockedError(f"{path} is held by another writer") from None
        data = fh.read()
        if not data or data.endswith(b"\n"):
            return None
        start = data.rfind(b"\n") + 1
        try:
            for line in data[:start].split(b"\n")[:-1]:
                Event.from_json(line.decode("utf-8"))
        except (ValueError, TypeError):
            return None
        try:
            Event.from_json(data[start:].decode("utf-8"))
        except (ValueError, TypeError):
            pass
        else:
            return None
        fh.truncate(start)
        fh.flush()
        os.fsync(fh.fileno())
        return data[start:].decode("utf-8", errors="replace")
    return None


def read_events(path: Path) -> list[Event]:
    """Parse every line; any invalid line raises with its line number.

    A torn final line raises too (fail closed); `repair_torn_tail` is the one way past it. Once a
    line carries `prev`, every later line must, and each must be the hash of the line before it
    (the first chained line follows the genesis value, or the last line written before the chain
    existed). A ledger with no `prev` at all is an older one and loads as it always did.
    """
    events: list[Event] = []
    expected = GENESIS
    chained = False
    lines = Path(path).read_bytes().split(b"\n")
    if lines[-1] == b"":  # the file ends in a newline (or is empty)
        lines.pop()
    for lineno, raw in enumerate(lines, start=1):
        try:
            event = Event.from_json(raw.decode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise LedgerCorruptError(f"{path}:{lineno}: {exc}") from exc
        if event.prev is not None:
            chained = True
            if event.prev != expected:
                raise LedgerCorruptError(
                    f"{path}:{lineno}: broken chain: `prev` is not the hash of the line before it"
                )
        elif chained:
            raise LedgerCorruptError(f"{path}:{lineno}: no `prev`, after lines that have one")
        expected = _sha256(raw)
        events.append(event)
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
