"""Append-only JSONL ledger: the single source of truth for every cent and decision in a run."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Callable, Hashable, Iterable
from contextlib import suppress
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import IO, Any

from antstreet import signing

LEDGER_VERSION = 1
# `prev` of the first line of a chained ledger. Fixed, so a deleted first line is detected too.
GENESIS = "0" * 64
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
# A signed line ends with its MAC, after the sorted keys, so the signed bytes are the line with this
# suffix replaced by "}" and a reader never has to re-serialise an event to check it.
_MAC_SUFFIX = r', "mac": "([0-9a-f]{64})"\}\Z'
_MAC_RE = re.compile(_MAC_SUFFIX)
_MAC_RE_B = re.compile(_MAC_SUFFIX.encode())
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
    AUDITED = "audited"  # `antstreet audit check`: the gate's verdict on someone else's change


AUDIT_ACTOR = "gate"  # the only actor whose `audited` event counts


def is_signed_kind(event: Event) -> bool:
    """The events the project's key signs: the investor's decisions, and the audit verdicts (a
    verdict is a record other people are shown, so a line edited or added by someone without the
    key must not read as one)."""
    return event.actor == "investor" or event.event is EventType.AUDITED


def audited(events: Iterable[Event]) -> list[Event]:
    """The `audited` events written by the gate. One from any other actor is not a verdict: the
    ledger accepts it as a line, readers of verdicts must not count it."""
    return [e for e in events if e.event is EventType.AUDITED and e.actor == AUDIT_ACTOR]


class Billing(StrEnum):
    API = "api"
    SUBSCRIPTION = "subscription"
    UNKNOWN = "unknown"


class LedgerError(Exception):
    """Base class for ledger failures."""


class LedgerCorruptError(LedgerError):
    """A line in the ledger file is not a valid event."""


class LedgerUnverifiedError(LedgerCorruptError):
    """The ledger parses and chains, but the investor key does not vouch for it: an investor event
    that is not signed by this project's key, or an anchor its tail does not match."""


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
        """The event of a line; a signed line's `mac` is the ledger's, not the event's."""
        if m := _MAC_RE.search(line):
            line = line[: m.start()] + "}"
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


def _last_line(path: Path) -> tuple[str, int]:
    """What the next line's `prev` must be (the hash of the file's last line, without its newline)
    and how many lines the file has.

    Reads the whole file once per open.
    """
    data = Path(path).read_bytes()
    if not data:
        return GENESIS, 0
    body = data.removesuffix(b"\n")
    return _sha256(body.rsplit(b"\n", 1)[-1]), body.count(b"\n") + 1


def _end_last_line(fh: IO[str], path: Path) -> None:
    """Make a file whose last line has no newline safe to append to, or refuse it.

    A complete event that only lost its newline gets one: nothing is lost, and its hash (what the
    next `prev` is) does not include the newline. A cut-off fragment is refused: a line appended
    to it is glued on and the file can no longer be repaired, and cutting it is `antstreet resume`'s
    decision (`repair_torn_tail`), which tells the investor what it removed.
    """
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    try:
        Event.from_json(data[data.rfind(b"\n") + 1 :].decode("utf-8"))
    except (ValueError, TypeError):
        raise LedgerCorruptError(
            f"{path}: the last line is cut off, so nothing can be appended to it; "
            "`antstreet resume` repairs it"
        ) from None
    fh.write("\n")
    fh.flush()
    os.fsync(fh.fileno())


class LedgerWriter:
    """Exclusive appender. Use as a context manager; a second writer on the same file is refused.

    With a `key_path` (`RunPaths.investor_key`) the project's investor key is created if needed
    when the writer opens, every line is signed (`mac`) and every investor event too (`data.sig`)
    as it is appended, and the ledger's tail is anchored after every append; see `signing.py`. All
    of it is done here so no writer can forget it.
    """

    def __init__(self, path: Path, key_path: Path | None = None) -> None:
        self.path = Path(path)
        self._key_path = key_path
        self._key: bytes | None = None
        self._fh: IO[str] | None = None
        self._prev = GENESIS
        self._lines = 0
        self._append_lock = threading.Lock()  # parallel slices append from several threads

    def __enter__(self) -> LedgerWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise LedgerLockedError(f"{self.path} is held by another writer") from None
        try:  # under the lock: nobody appends meanwhile
            _end_last_line(fh, self.path)
            self._prev, self._lines = _last_line(self.path)
            if self._key_path is not None:  # never append to a ledger the key does not vouch for
                read_events(self.path, self._key_path)  # before a key is created: a lost one shows
                run = self.path.parent.name
                if self._lines and not signing.anchor_path(self._key_path, run).exists():
                    # with no key the read above could check nothing; signing on top would launder
                    raise LedgerUnverifiedError(
                        _unadopted(self.path, run, unsigned_lines(self.path), self._lines)
                    )
                self._key = signing.load_or_create_key(self._key_path)
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
        """Write one line, signed when the writer has a key (loaded when it opened, so signing
        cannot fail here). The line is durable before the anchor is attempted, so a failing anchor
        never loses a record."""
        if self._fh is None:
            raise LedgerError("writer is not open; use `with LedgerWriter(path) as w:`")
        with self._append_lock:  # the link, the write and the next link are one step
            event = replace(event, prev=self._prev)
            if self._key is not None and is_signed_kind(event):
                event = signing.sign(self._key, event)
            # serialise first so a bad event never leaves a partial line
            line = event.to_json()
            if self._key is not None:
                mac = signing.line_mac(self._key, self.path.parent.name, _sha256(line.encode()))
                line = f'{line[:-1]}, "mac": "{mac}"}}'
            self._fh.write(line + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())  # money records must survive a crash right after append
            self._prev = _sha256(line.encode("utf-8"))
            self._lines += 1
            if self._key_path is not None:
                signing.write_anchor(self._key_path, self.path.parent.name, self._lines, self._prev)


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


type _Mark = tuple[str, str] | None  # a signed line's (hash of the signed bytes, mac)

_SETTLE_TRIES = 20  # 20 x 5 ms: a torn tail no writer finishes costs a reader 100 ms, then fails
_SETTLE_WAIT = 0.005


def _settled(path: Path) -> bytes:
    """The file's bytes, re-read briefly while its last line has no newline.

    Readers take no lock, and one `write` is not atomic against a concurrent `read`: Linux makes
    an append visible a page at a time (CI run 38042874252 read a line cut at byte 4096). A line
    in flight is whole within microseconds; a torn tail left by a crash never is, and is judged
    exactly as before once the wait runs out. Only the last read is used, and it is
    parsed and checked in full, so no state is accepted that a single read would have refused.
    """
    data = Path(path).read_bytes()
    for _ in range(_SETTLE_TRIES):
        if not data or data.endswith(b"\n"):
            break
        time.sleep(_SETTLE_WAIT)
        data = Path(path).read_bytes()
    return data


def _parse(path: Path) -> tuple[list[Event], list[str], list[_Mark]]:
    """Every event, the hash of every line, and the signature of every signed line."""
    events: list[Event] = []
    hashes: list[str] = []
    marks: list[_Mark] = []
    expected = GENESIS
    chained = False
    lines = _settled(path).split(b"\n")
    if lines[-1] == b"":  # the file ends in a newline (or is empty)
        lines.pop()
    for lineno, raw in enumerate(lines, start=1):
        m = _MAC_RE_B.search(raw)
        body = raw[: m.start()] + b"}" if m else raw
        try:
            event = Event.from_json(body.decode("utf-8"))
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
        hashes.append(expected)
        events.append(event)
        marks.append((_sha256(body), m.group(1).decode()) if m else None)
    return events, hashes, marks


def _unadopted(path: Path, run: str, unsigned: int, lines: int) -> str:
    return (
        f"{path}: {unsigned} of {lines} lines are unsigned and the run has no anchor: either older "
        "than line signing or rewritten without the key. If you know the run is genuine, accept "
        f"it as it is now with `antstreet verify {run} --adopt-unsigned`"
    )


def adopt_unsigned(path: Path, key_path: Path) -> int:
    """The investor's decision (`antstreet verify RUN --adopt-unsigned`) to vouch for a run's
    ledger as
    it is now: every check `read_events` makes but the anchor's, then an anchor for the current
    tail, so later reads and appends verify as for any signed run. Returns the unsigned lines it
    adopted; 0, changing nothing, when the run already has an anchor (which must verify). Never
    called by the engine: what it accepts is exactly what the anchor exists to refuse."""
    path = Path(path)
    run = path.parent.name
    with LedgerWriter(path):  # the lock only: no key, so it writes nothing
        if signing.anchor_path(key_path, run).exists():
            read_events(path, key_path)
            return 0
        events, hashes, marks = _parse(path)
        anchor_file = signing.anchor_path(key_path, run)
        try:  # a key is created only for a ledger no key ever signed: a lost one must show
            key = signing.load_key(key_path) if any(marks) else signing.load_or_create_key(key_path)
        except signing.SigningError as exc:
            raise LedgerUnverifiedError(f"{path}: {exc}") from None
        _vouched(path, run, anchor_file, key, events, hashes, marks, None, adopting=True)
        signing.write_anchor(key_path, run, len(hashes), hashes[-1] if hashes else GENESIS)
        return marks.count(None)


def unsigned_lines(path: Path) -> int:
    """How many lines carry no `mac`: lines written before line signing or by a writer with no
    key. With a key, `read_events` refuses one after a signed line, so they are always first."""
    return _parse(path)[2].count(None)


# kn: every open re-reads and re-verifies the whole file, O(n) per CLI call: 79 ms to read and 99 ms
# to open a writer at 10,000 lines (4 MB), so it only matters past about 25,000 lines per ledger.
# Upgrade path: cache the parse by (size, mtime, hash of the last line) and still check the anchor.
def read_events(path: Path, key_path: Path | None = None) -> list[Event]:
    """Parse every line; any invalid line raises with its line number.

    A torn final line raises too (fail closed); `repair_torn_tail` is the one way past it. Once a
    line carries `prev`, every later line must, and each must be the hash of the line before it
    (the first chained line follows the genesis value, or the last line written before the chain
    existed). A ledger with no `prev` at all is an older one and loads as it always did.

    With a `key_path` (`RunPaths.investor_key`) the project's investor key must also vouch for what
    a reader trusts: see `_vouched`. Every reader that acts on an investor event passes it.
    """
    if key_path is None:
        return _parse(path)[0]
    try:
        key = signing.load_key(key_path)
        run = Path(path).parent.name
        # Anchor first: a writer appends before it re-anchors, so a ledger read after the anchor is
        # never shorter than it unless lines were dropped.
        anchor = None if key is None else signing.read_anchor(key_path, key, run)
        events, hashes, marks = _parse(path)
        _vouched(path, run, signing.anchor_path(key_path, run), key, events, hashes, marks, anchor)
    except signing.SigningError as exc:
        raise LedgerUnverifiedError(f"{path}: {exc}") from None
    return events


def _vouched(
    path: Path,
    run: str,
    anchor_file: Path,
    key: bytes | None,
    events: list[Event],
    hashes: list[str],
    marks: list[_Mark],
    anchor: signing.Anchor | None,
    *,
    adopting: bool = False,
) -> None:
    """Raise LedgerUnverifiedError unless the key vouches for the ledger.

    Every investor event must verify; when a key exists an unsigned one is accepted only where the
    line has no `prev` (older than the chain), and a signed one is refused when the key is gone.
    The first `anchor.lines` lines must be the ones the anchor recorded; lines past that need only
    their `mac` (a writer appends before it re-anchors, so a crash, or a reader racing it, sees
    one).
    A missing anchor is accepted only when the ledger holds no signed line and no v2-signed event:
    a ledger that has one was written by code that anchors, so its anchor was deleted. A ledger
    with unsigned lines and no anchor is refused too: it is older than line signing or was rewritten
    without the key, and only the investor can tell which (`adopt_unsigned`, which passes
    `adopting` to skip both anchor rules once).
    From its first signed line on, every line must carry a `mac` that verifies, so a line edited,
    forged or appended without the key is refused wherever it is; the lines before the first
    signed one are covered by its `prev`.
    """
    signed_from = next((i for i, mark in enumerate(marks) if mark is not None), None)
    stamped = signed_from is not None
    if key is None and signed_from is not None:
        raise LedgerUnverifiedError(
            f"{path}: its lines are signed but the investor key is missing; restore "
            f"{anchor_file.parent.parent / signing.KEY_FILE} from a backup (a new key cannot "
            "verify them)"
        )
    for lineno, e in enumerate(events, start=1):
        if not is_signed_kind(e):
            continue
        signed = signing.SIG_KEY in e.data
        stamped = stamped or str(e.data.get(signing.SIG_KEY, "")).startswith(signing.SIG_V2)
        older = key is None or e.prev is None  # with no key nothing can be checked
        ok = older if not signed else key is not None and signing.verify(key, e)
        if not ok:
            kind = f"{'investor ' if e.actor == 'investor' else ''}`{e.event}` event"
            by = "" if e.actor == "investor" else f" by {e.actor}"
            raise LedgerUnverifiedError(
                f"{path}:{lineno}: {kind}{by} whose signature does not verify "
                "against .boss/investor.key (forged, edited, moved, or the key was replaced)"
            )
    if key is None:
        if anchor_file.exists():
            raise LedgerUnverifiedError(f"{path}: has an anchor but the investor key is missing")
    elif anchor is None:
        if stamped and not adopting:
            raise LedgerUnverifiedError(
                f"{path}: its anchor {anchor_file} is missing, so dropped lines could not be seen"
            )
        if (unsigned := marks.count(None)) and not adopting:
            raise LedgerUnverifiedError(_unadopted(path, run, unsigned, len(marks)))
    elif len(events) < anchor.lines:
        raise LedgerUnverifiedError(
            f"{path}: has {len(events)} lines but its anchor records {anchor.lines}: "
            f"{anchor.lines - len(events)} line(s) were dropped from the end"
        )
    elif (hashes[anchor.lines - 1] if anchor.lines else GENESIS) != anchor.last:
        raise LedgerUnverifiedError(
            f"{path}: line {anchor.lines} is not the line its anchor records (it was edited)"
        )
    if key is None or signed_from is None:
        return
    for lineno, mark in enumerate(marks[signed_from:], start=signed_from + 1):
        if mark is None:
            raise LedgerUnverifiedError(
                f"{path}:{lineno}: an unsigned line after signed ones (written without the "
                "investor key)"
            )
        if not signing.verify_line(key, run, *mark):
            raise LedgerUnverifiedError(
                f"{path}:{lineno}: a line whose signature does not verify against "
                ".boss/investor.key (edited, forged, from another run, or the key was replaced)"
            )


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
