"""The investor's per-project secret and the HMAC it puts on an approval.

The key lives in `<project>/.boss/investor.key` (hex, mode 0600, created on first use). It is read
only to sign and to verify: it is never logged, printed, put in an error message or passed to a
child process. A worker's tool rules confine it to its own workspace and the gate's sandbox reads
nothing outside its own folder, so a worker can edit the ledger and recompute its hash chain but
cannot produce a signature (docs/THREAT_MODEL.md, T46).
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
from pathlib import Path
from typing import Any

from boss.ledger import Event

KEY_FILE = "investor.key"
SIG_KEY = "sig"  # the key in an `approved` event's `data` that holds the signature
_KEY_BYTES = 32


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


def _digest(key: bytes, run: str, round: int, data: Mapping[str, Any]) -> str:
    body = {k: v for k, v in data.items() if k != SIG_KEY}
    message = json.dumps(
        {"purpose": "boss approval v1", "run": run, "round": round, "data": body},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()


def signed(key: bytes, run: str, round: int, data: Mapping[str, Any]) -> dict[str, Any]:
    """`data` with its signature added. The signature covers the run id, the round and every
    other key of `data`, so an approval cannot be moved to another run or edited."""
    return {**data, SIG_KEY: _digest(key, run, round, data)}


def verify(key: bytes, event: Event) -> bool:
    sig = event.data.get(SIG_KEY)
    if not isinstance(sig, str):
        return False
    expected = _digest(key, event.run, event.round, event.data)
    return hmac.compare_digest(sig.encode(), expected.encode())  # bytes: str must be ASCII
