"""The investor's per-project secret, the HMAC it puts on every investor event, and the anchor.

The key lives in `<project>/.boss/investor.key` (hex, mode 0600, created on first use). It is read
only to sign and to verify: it is never logged, printed, put in an error message or passed to a
child process. A worker's tool rules confine it to its own workspace and the gate's sandbox reads
nothing outside its own folder, so a worker can edit the ledger and recompute its hash chain but
cannot produce a signature (docs/THREAT_MODEL.md, T46).

An investor event's signature covers every field of its line, `prev` included, so it cannot be
edited, moved, replayed at another place in the ledger, or survive an edit of any line before it.
The anchor (`<project>/.boss/anchors/<run>`) is the same key's HMAC of the ledger's line count and
last line hash, which the chain alone cannot protect.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import stat
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # ledger imports this module
    from boss.ledger import Event

KEY_FILE = "investor.key"
ANCHOR_DIR = "anchors"
SIG_KEY = "sig"  # the key in an investor event's `data` that holds the signature
SIG_V2 = "v2:"  # a signature over the whole line; a bare hex one is the first form (approvals)
_KEY_BYTES = 32
_ANCHOR_MAX_BYTES = 4_096


class SigningError(Exception):
    """The investor key cannot be used. Never carries any of the key."""


def key_path(project: Path) -> Path:
    return Path(project) / ".boss" / KEY_FILE


def load_key(path: Path) -> bytes | None:
    """The key, or None when there is no key file. A key that is a symlink, not a regular file,
    readable by group or others, or not 32 bytes of hex raises SigningError."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SigningError(f"cannot open the investor key {path}: {exc.strerror}") from None
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:  # fdopen would reject a directory
        os.close(fd)
        raise SigningError(
            f"the investor key {path} must be a regular file readable by its owner only; "
            "chmod 600 it"
        )
    with os.fdopen(fd, "rb") as fh:
        text = fh.read(4 * _KEY_BYTES)
    try:
        key = bytes.fromhex(text.decode("ascii").strip())
    except ValueError:  # no `from exc`: the message of a decode error can quote the bytes
        raise SigningError(f"{path} is not an investor key written by boss") from None
    if len(key) != _KEY_BYTES:
        raise SigningError(f"{path} is not an investor key written by boss")
    return key


def load_or_create_key(path: Path) -> bytes:
    """The key, created with mode 0600 if the project has none yet. The key is written to a private
    temporary file and linked into place, so a crash never leaves a half-written key and a second
    process cannot replace one that exists."""
    if (key := load_key(path)) is not None:
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(secrets.token_bytes(_KEY_BYTES).hex() + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        with contextlib.suppress(FileExistsError):  # another process won; use its key
            os.link(tmp, path)
    finally:
        os.unlink(tmp)
    key = load_key(path)
    assert key is not None
    return key


def _mac(key: bytes, message: Mapping[str, Any]) -> str:
    text = json.dumps(message, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


def _digest_v1(key: bytes, event: Event) -> str:
    """The first form, which only `approved` events carry: run, round and data."""
    body = {k: v for k, v in event.data.items() if k != SIG_KEY}
    return _mac(
        key, {"purpose": "boss approval v1", "run": event.run, "round": event.round, "data": body}
    )


def _digest_v2(key: bytes, event: Event) -> str:
    """Every field of the line, `prev` and the cost included, but the signature itself."""
    body = asdict(event)
    body["data"] = {k: v for k, v in event.data.items() if k != SIG_KEY}
    return _mac(key, {"purpose": "boss investor event v2", **body})


def sign(key: bytes, event: Event) -> Event:
    """`event` with its signature in `data`. It needs the `prev` the writer has just set: that
    link is what ties the signature to one place in one ledger."""
    if event.prev is None:
        raise ValueError("an event is signed after its `prev` is set")
    return replace(event, data={**event.data, SIG_KEY: SIG_V2 + _digest_v2(key, event)})


def verify(key: bytes, event: Event) -> bool:
    sig = event.data.get(SIG_KEY)
    if not isinstance(sig, str):
        return False
    if sig.startswith(SIG_V2):
        expected = SIG_V2 + _digest_v2(key, event)
    elif event.event.value == "approved":  # the first form was never used for anything else
        expected = _digest_v1(key, event)
    else:
        return False
    return hmac.compare_digest(sig.encode(), expected.encode())  # bytes: str must be ASCII


@dataclass(frozen=True, slots=True)
class Anchor:
    lines: int  # how many lines the ledger had when it was written
    last: str  # SHA-256 of the last of them, without its newline


def anchor_path(key_file: Path, run: str) -> Path:
    return key_file.parent / ANCHOR_DIR / run


def _anchor_mac(key: bytes, run: str, lines: int, last: str) -> str:
    return _mac(key, {"purpose": "boss ledger anchor v1", "run": run, "lines": lines, "last": last})


def write_anchor(key_file: Path, run: str, lines: int, last: str) -> None:
    """Record the ledger's tail, replacing the previous record atomically. Does nothing when the
    project has no key yet."""
    key = load_key(key_file)
    if key is None:
        return
    target = anchor_path(key_file, run)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"lines": lines, "last": last, "mac": _anchor_mac(key, run, lines, last)})
    tmp = target.with_name(f"{run}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(body + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    dir_fd = os.open(target.parent, os.O_RDONLY)  # make the rename itself survive a crash
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def read_anchor(key_file: Path, key: bytes, run: str) -> Anchor | None:
    """The recorded tail, None when there is no anchor file, SigningError when there is one that
    was not written with this key for this run."""
    path = anchor_path(key_file, run)
    try:
        with path.open("rb") as fh:
            raw = fh.read(_ANCHOR_MAX_BYTES)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise SigningError(f"cannot read the ledger anchor {path}: {exc.strerror}") from None
    try:
        found = json.loads(raw)
        lines, last, mac = found["lines"], found["last"], found["mac"]
        valid = type(lines) is int and isinstance(last, str) and isinstance(mac, str)
    except (ValueError, KeyError, TypeError):
        valid = False
    if not valid or not hmac.compare_digest(
        mac.encode(errors="replace"), _anchor_mac(key, run, lines, last).encode()
    ):
        raise SigningError(f"the ledger anchor {path} does not verify against the investor key")
    return Anchor(lines, last)
