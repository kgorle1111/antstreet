"""Preflight: every way a run can fail before it starts, each with a one-line fix.

Expected failures (missing binary, non-zero exit, timeout, unparsable output) become failed
checks, never exceptions. Nothing here prints or logs environment values.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from boss.errors import Outcome, classify
from boss.stream import StreamReader
from boss.worker import CLI, MIN_CLI_VERSION, parse_version, uses_api_key

_PROBE_TIMEOUT_S = 20
_LIVE_TIMEOUT_S = 120
_LOGIN_FIX = "claude auth login"
_MIN_CLI = ".".join(map(str, MIN_CLI_VERSION))
_MIN_PYTHON = (3, 12)


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str  # what was found
    fix: str  # one-line next step; empty string when ok


def _pass(name: str, detail: str) -> DoctorCheck:
    return DoctorCheck(name, True, detail, "")


def _fail(name: str, detail: str, fix: str) -> DoctorCheck:
    return DoctorCheck(name, False, detail, fix)


def _skipped(name: str, because: str) -> DoctorCheck:
    return _fail(name, f"skipped: {because}", f"fix {because} first")


def _run(
    argv: list[str], env: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[str] | str:
    """The finished process, or a one-line reason it could not run to completion."""
    try:
        return subprocess.run(
            argv, env=dict(env), stdin=subprocess.DEVNULL, capture_output=True, text=True,
            timeout=timeout,
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        return f"timed out after {timeout}s"
    except (OSError, ValueError) as exc:
        return f"could not run: {exc.__class__.__name__}"


def _check_python() -> DoctorCheck:
    found = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info >= _MIN_PYTHON:
        return _pass("python", found)
    return _fail("python", f"{found}, need 3.12 or newer", "run boss with Python 3.12+")


def _check_platform() -> DoctorCheck:
    if os.name == "posix":
        return _pass("platform", "posix")
    return _fail("platform", f"{os.name} is unsupported", "run boss on macOS or Linux")


def _check_pytest() -> DoctorCheck:
    if importlib.util.find_spec("pytest") is not None:
        return _pass("pytest", "importable")
    return _fail("pytest", "not importable; the gate runs checks with it", "uv add pytest")


def _check_cli(executable: str, env: Mapping[str, str]) -> tuple[DoctorCheck, str | None]:
    found = shutil.which(executable, path=env.get("PATH"))
    if found:
        return _pass("claude cli", found), found
    fix = "install Claude Code, then put `claude` on PATH or pass its absolute path"
    return _fail("claude cli", f"{executable!r} not found", fix), None


def _check_version(path: str, env: Mapping[str, str]) -> DoctorCheck:
    fix = f"update Claude Code to {_MIN_CLI} or newer (claude update)"
    done = _run([path, "--version"], env, _PROBE_TIMEOUT_S)
    if isinstance(done, str):
        return _fail("claude version", f"--version {done}", fix)
    version = parse_version(done.stdout) if done.returncode == 0 else None
    if version is None:
        return _fail("claude version", f"unparsable output (exit {done.returncode})", fix)
    text = ".".join(map(str, version))
    if version < MIN_CLI_VERSION:
        return _fail("claude version", f"{text} is below {_MIN_CLI}", fix)
    return _pass("claude version", text)


def _logged_in(path: str, env: Mapping[str, str]) -> bool | str:
    """True/False from `auth status`, or a one-line reason it could not be read."""
    done = _run([path, "auth", "status"], env, _PROBE_TIMEOUT_S)
    if isinstance(done, str):
        return f"auth status {done}"
    try:
        status = json.loads(done.stdout)
    except ValueError:
        status = None
    flag = status.get("loggedIn") if isinstance(status, dict) else None
    if isinstance(flag, bool):
        return flag
    return f"auth status gave unparsable output (exit {done.returncode})"


def _live_call(path: str, env: Mapping[str, str], *, api_key: bool) -> DoctorCheck:
    isolation = "--bare" if api_key else "--safe-mode"
    argv = [
        path, "--print", "--output-format", "json", isolation, "--model", "haiku",
        "--tools", "", "--max-budget-usd", "0.05", "Reply with the single word: ok",
    ]  # fmt: skip
    done = _run(argv, env, _LIVE_TIMEOUT_S)
    if isinstance(done, str):
        return _fail("login", f"live call {done}", "check your network, then re-run with --live")
    reader = StreamReader()
    for line in done.stdout.splitlines():
        reader.feed(line)
    outcome = classify(reader.signals())
    if outcome is Outcome.COMPLETED:
        return _pass("login", "verified with one live call")
    if outcome is Outcome.LOGIN:
        return _fail("login", "the API rejected the credentials", _LOGIN_FIX)
    return _fail("login", f"live call ended as {outcome.name}", "re-run with --live later")


def _check_login(path: str, env: Mapping[str, str], *, live: bool) -> DoctorCheck:
    api_key = uses_api_key(env)
    if api_key and not live:
        return _pass(
            "login", "API key set; bare mode with an API key has not been verified by this project"
        )
    if not api_key:
        state = _logged_in(path, env)
        if isinstance(state, str):
            return _fail("login", state, _LOGIN_FIX)
        if not state:
            return _fail("login", "not logged in", _LOGIN_FIX)
        if not live:
            detail = "logged in per `auth status` (reported, not verified; use boss doctor --live)"
            return _pass("login", detail)
    return _live_call(path, env, api_key=api_key)


def _check_writable(cwd: Path) -> DoctorCheck:
    folder = cwd / ".boss"
    probe = folder / f".doctor-{os.getpid()}"
    try:
        folder.mkdir(exist_ok=True)
        probe.write_text("probe")
        probe.unlink()
    except OSError as exc:
        fix = f"make {folder} writable (chmod u+w) or run boss from another folder"
        return _fail("writable folder", f"{folder}: {exc.__class__.__name__}", fix)
    return _pass("writable folder", str(folder))


def run_doctor(
    env: Mapping[str, str], cwd: Path, *, live: bool = False, executable: str = CLI
) -> list[DoctorCheck]:
    checks = [_check_python(), _check_platform(), _check_pytest()]
    cli, path = _check_cli(executable, env)
    checks.append(cli)
    if path is None:
        checks += [_skipped("claude version", "claude cli"), _skipped("login", "claude cli")]
    else:
        checks += [_check_version(path, env), _check_login(path, env, live=live)]
    return [*checks, _check_writable(cwd)]


def render_doctor(checks: Sequence[DoctorCheck]) -> str:
    lines: list[str] = []
    for check in checks:
        lines.append(f"{'ok  ' if check.ok else 'FAIL'}  {check.name}: {check.detail}")
        if not check.ok:
            lines.append(f"        fix: {check.fix}")
    failed = sum(not check.ok for check in checks)
    lines.append(
        f"{failed} of {len(checks)} checks failed" if failed else f"all {len(checks)} checks ok"
    )
    return "\n".join(lines)
