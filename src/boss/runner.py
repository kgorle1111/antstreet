"""Run one worker slice as a child process: stream, meter, verify isolation, stop cleanly."""

from __future__ import annotations

import collections
import contextlib
import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, cast

from boss.errors import Outcome, classify
from boss.redact import redact
from boss.stream import StreamReader, Usage
from boss.worker import (
    CLI,
    SliceSpec,
    build_command,
    model_id_of,
    require_isolation,
    uses_api_key,
    with_thinking,
)

DEFAULT_TIMEOUT_S = 15 * 60.0
DEFAULT_GRACE_S = 5.0
STDERR_TAIL_LINES = 50
DEFAULT_MAX_LOG_BYTES = 50 * 2**20  # a worker that prints without end must not fill the disk
LOG_CUT = '{"type": "boss", "note": "log cut: the size limit was reached"}\n'
# A worker could plant these to run code or tools outside its whitelist on the next resume.
FORBIDDEN_WORKSPACE_ENTRIES = (".claude", ".mcp.json")
_EOF = object()


class WorkspaceError(Exception):
    """The workspace is unsafe to launch a worker in."""


@dataclass(frozen=True, slots=True)
class SliceRun:
    outcome: Outcome
    usage: Usage
    status: dict[str, Any] | None
    session_id: str | None
    exit_code: int | None
    duration_s: float
    log_path: Path
    denials: list[dict[str, Any]] = field(default_factory=list)
    rate_limit: dict[str, Any] | None = None
    stderr_tail: str = ""
    model_id: str | None = None  # the model the CLI's init event says it ran


def run_slice(
    spec: SliceSpec,
    workspace: Path,
    log_path: Path,
    *,
    env: Mapping[str, str],
    timeout_s: float = DEFAULT_TIMEOUT_S,
    grace_s: float = DEFAULT_GRACE_S,
    executable: str = CLI,
    known_secrets: Iterable[str] = (),
    stop: threading.Event | None = None,
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
) -> SliceRun:
    """Run one slice to completion, timeout or refusal. Setting `stop` from another thread ends
    it the way a timeout does: the worker is interrupted and its final result still read.

    Raises IsolationError (after stopping the process) if the worker did not start isolated.
    """
    workspace = Path(os.path.realpath(workspace))  # path rules match only the canonical path
    check_workspace(workspace)
    argv = build_command(spec, api_key=uses_api_key(env))
    argv[0] = executable
    env = with_thinking(env, spec.thinking_tokens)
    secrets = [*known_secrets, *(v for k, v in env.items() if k == "ANTHROPIC_API_KEY")]
    log_path.parent.mkdir(parents=True, exist_ok=True)

    reader = StreamReader()
    stderr_tail: collections.deque[str] = collections.deque(maxlen=STDERR_TAIL_LINES)
    lines: queue.Queue[object] = queue.Queue()
    start = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=workspace,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True).start()
    drain = threading.Thread(target=_drain, args=(proc.stderr, stderr_tail), daemon=True)
    drain.start()

    timed_out = False
    try:
        with log_path.open("a", encoding="utf-8") as log:
            timed_out = _consume(
                proc, lines, reader, log, secrets, start + timeout_s, grace_s, stop, max_log_bytes
            )
        if not timed_out:
            with contextlib.suppress(subprocess.TimeoutExpired):  # finally stops it if needed
                proc.wait(timeout=grace_s)
    finally:
        if proc.poll() is None:
            _stop(proc, grace_s)
        _kill_group(proc.pid)  # reap anything the worker left behind in its process group

    drain.join(timeout=grace_s)  # the outcome may rest on the last stderr line
    stderr_text = redact("".join(stderr_tail), secrets)
    return SliceRun(
        outcome=classify(reader.signals(timed_out=timed_out, stderr_tail=stderr_text)),
        usage=reader.usage(),
        status=reader.status,
        session_id=reader.session_id,
        exit_code=proc.returncode,
        duration_s=time.monotonic() - start,
        log_path=log_path,
        denials=reader.denials,
        rate_limit=reader.rate_limit,
        stderr_tail=stderr_text,
        model_id=model_id_of(reader.init),
    )


def check_workspace(workspace: Path) -> None:
    """Refuse a workspace holding agent configuration at any depth: a worker can plant one under
    a subdirectory and work there, so checking only the top level is not enough.

    Matches by name on every entry (symlinks included, never followed), so a dangling or
    out-of-tree link named `.claude` is refused as well.
    """
    if not workspace.is_dir():
        raise WorkspaceError(f"workspace {workspace} does not exist")

    def unreadable(exc: OSError) -> None:
        raise WorkspaceError(f"cannot inspect workspace: {exc}")  # an unread dir could hide one

    planted = sorted(
        Path(root, name).relative_to(workspace).as_posix()
        for root, dirs, files in os.walk(workspace, onerror=unreadable)  # followlinks=False
        for name in (*dirs, *files)
        if name in FORBIDDEN_WORKSPACE_ENTRIES
    )
    if planted:
        raise WorkspaceError(f"workspace contains agent configuration: {planted}")


def _consume(
    proc: subprocess.Popen[str],
    lines: queue.Queue[object],
    reader: StreamReader,
    log: IO[str],
    secrets: list[str],
    deadline: float,
    grace_s: float,
    stop: threading.Event | None = None,
    max_log_bytes: int = DEFAULT_MAX_LOG_BYTES,
) -> bool:
    """Feed stdout to the reader until EOF. Returns True if the deadline was hit.

    After a timeout it keeps reading: SIGINT lets the CLI print a final result with the slice's
    cost, and dropping that line would turn a known cost into an unknown one.
    """
    checked_init = timed_out = False
    logged = 0  # bytes written to the log; past the cap the stream is still read, not stored
    while True:
        remaining = deadline - time.monotonic()
        if (remaining <= 0 or (stop is not None and stop.is_set())) and not timed_out:
            timed_out = True
            _stop(proc, grace_s)
        try:
            item = lines.get(timeout=grace_s if timed_out else max(0.01, min(remaining, 0.5)))
        except queue.Empty:
            if timed_out:
                return True  # stopped, and nothing more is coming
            continue
        if item is _EOF:
            return timed_out
        line = cast(str, item)
        if logged <= max_log_bytes:
            text = redact(line if line.endswith("\n") else line + "\n", secrets)
            logged += len(text.encode("utf-8", errors="replace"))
            log.write(text if logged <= max_log_bytes else LOG_CUT)
        reader.feed(line)
        # Init passed with zero hook events, so any hook event counted since is a late one.
        if reader.init is not None and (not checked_init or reader.hook_events):
            checked_init = True
            # Raises on a violation; run_slice's finally block stops the process.
            require_isolation(reader.init, hook_events=reader.hook_events)


def _pump(stream: IO[str] | None, lines: queue.Queue[object]) -> None:
    if stream is not None:
        for line in stream:
            lines.put(line)
    lines.put(_EOF)


def _drain(stream: IO[str] | None, tail: collections.deque[str]) -> None:
    if stream is not None:
        for line in stream:
            tail.append(line)


def _stop(proc: subprocess.Popen[str], grace_s: float) -> None:
    """SIGINT ends the current turn cleanly; then SIGTERM, then SIGKILL, to the process group."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:  # macOS: the leader already exited; its group cannot be signalled
            proc.wait()
            return
        try:
            proc.wait(timeout=grace_s)
            return
        except subprocess.TimeoutExpired:
            continue
    _kill_group(proc.pid)
    proc.wait()


def _kill_group(pid: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
