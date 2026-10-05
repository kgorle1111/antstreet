"""An OS sandbox around one check process: no network, writes only in one folder, reads only what
Python needs. The gate builds a command with `Sandbox.wrap`; nothing here runs a check.

Paths never become part of profile text: on macOS they travel as `sandbox-exec -D` parameters and
on Linux as `bwrap` arguments, so a directory named `"))(allow default)((` grants access to exactly
that directory. The profile text depends only on how many readable paths there are.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from pathlib import Path

_PROBE_TIMEOUT_S = 30
TOOLS = {"Darwin": "sandbox-exec", "Linux": "bwrap"}


class SandboxMode(StrEnum):
    AUTO = "auto"  # sandbox when the platform has a working tool, run unsandboxed otherwise
    REQUIRE = "require"  # refuse to run a check without a sandbox
    OFF = "off"


class SandboxUnavailable(Exception):
    """A sandbox was required and this machine has no working tool. Carries the fix."""


# Deny by default; every line below is an exception found by running the gate's own pytest command
# on macOS 26 (docs/SANDBOX.md). Not granted: network, mach services other than the user lookup,
# reads outside the list, writes outside WRITABLE, signals to processes outside the sandbox.
_SEATBELT_HEAD = """\
(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow signal (target same-sandbox))
(allow sysctl-read)
(allow ipc-posix-sem)
(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))
(allow file-read-metadata)
(allow file-read*
  (literal "/")
  (literal "/dev/null")
  (subpath "/usr/share/locale")
  (subpath "/private/var/db/timezone")
  (subpath "/usr/share/zoneinfo.default")
  (subpath (param "WRITABLE"))"""
_SEATBELT_TAIL = """\
(allow file-write* (literal "/dev/null") (subpath (param "WRITABLE")))
"""


def seatbelt_profile(readable_count: int) -> str:
    extra = "".join(f'\n  (subpath (param "R{i}"))' for i in range(readable_count))
    return f"{_SEATBELT_HEAD}{extra})\n{_SEATBELT_TAIL}"


def _absolute(path: Path) -> str:
    text = os.fspath(path)
    if not os.path.isabs(text):
        raise ValueError(f"sandbox paths must be absolute and resolved, got {text!r}")
    return text


def seatbelt_argv(
    executable: str, argv: Sequence[str], *, writable: Path, readable: Sequence[Path]
) -> list[str]:
    params = {"WRITABLE": _absolute(writable)}
    params.update({f"R{i}": _absolute(p) for i, p in enumerate(readable)})
    out = [executable]
    for key, value in params.items():
        out += ["-D", f"{key}={value}"]
    return [*out, "-p", seatbelt_profile(len(readable)), *argv]


# kn: root read-only with /home, /root, /tmp and /run hidden; not run on this machine (no bwrap on
# macOS). /proc is remounted inside a new PID namespace, or the host's /proc/<pid>/environ would
# leak the caller's environment. --unshare-ipc hides the host's SysV shared memory, semaphores and
# message queues (the seatbelt profile denies them by default); /dev/shm is not covered by it but
# `--dev /dev` replaces it. No --new-session: the gate already starts the check in its own
# session, and bwrap's setsid() fails for a process that already leads one. Everything else on the
# host stays readable, so a project under /srv, /opt or /work would expose `<project>/.boss`
# (investor key, ledger): `hidden` paths are masked after the four roots and after every bind
# that is not inside one, but before the binds that are (bwrap applies mounts in argv order): an
# ancestor bind after a mask would re-expose the secret; one inside a mask re-exposes only itself.
# Upgrade path: an allowlist root (--ro-bind /usr, /lib*, /bin) once it can be verified on a Linux
# host.
_BWRAP_HIDDEN_ROOTS = ("/home", "/root", "/tmp", "/run")


def _mask(path: Path) -> list[str]:
    """A directory becomes an empty tmpfs, a file an empty file; a missing path hides nothing."""
    text = _absolute(path)
    if path.is_dir():
        return ["--tmpfs", text]
    return ["--ro-bind", "/dev/null", text] if path.exists() else []


def bwrap_argv(
    executable: str,
    argv: Sequence[str],
    *,
    writable: Path,
    readable: Sequence[Path],
    hidden: Sequence[Path] = (),
) -> list[str]:
    out = [
        executable, "--die-with-parent", "--unshare-net", "--unshare-pid", "--unshare-ipc",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/home", "--tmpfs", "/root", "--tmpfs", "/tmp", "--tmpfs", "/run",
    ]  # fmt: skip
    masks = {
        _absolute(path): _mask(path)
        for path in hidden
        # Under a root above it is already gone, and a mount point there no longer exists.
        if not any(_absolute(path).startswith(f"{root}/") for root in _BWRAP_HIDDEN_ROOTS)
    }
    masks = {path: part for path, part in masks.items() if part}

    def under_mask(path: Path) -> bool:
        text = _absolute(path)
        return any(text == m or text.startswith(f"{m}/") for m in masks)

    # A bind of an ancestor of a mask would re-expose the secret, so it goes first; a bind inside
    # a mask goes after it, re-exposing only itself.
    for inside in (False, True):
        if inside:
            for part in masks.values():
                out += part
        for path in readable:
            if under_mask(path) == inside:
                out += ["--ro-bind", _absolute(path), _absolute(path)]
    out += ["--bind", _absolute(writable), _absolute(writable)]
    return [*out, "--", *argv]


@dataclass(frozen=True, slots=True)
class Sandbox:
    name: str  # "sandbox-exec" or "bwrap"
    executable: str  # absolute path found by detect(), so a later PATH change cannot swap it

    def wrap(
        self,
        argv: Sequence[str],
        *,
        writable: Path,
        readable: Sequence[Path],
        hidden: Sequence[Path] = (),
    ) -> list[str]:
        """`argv` run inside the sandbox. Path arguments must be absolute and resolved.

        `hidden` are secret folders or files to mask on Linux, where the root is readable. macOS
        needs nothing: its profile denies every read that is not listed.
        """
        if not argv or argv[0].startswith("-"):
            raise ValueError(f"cannot sandbox a command that starts with {argv[:1]!r}")
        if self.name == "sandbox-exec":
            return seatbelt_argv(self.executable, argv, writable=writable, readable=readable)
        return bwrap_argv(
            self.executable, argv, writable=writable, readable=readable, hidden=hidden
        )


def python_readable() -> tuple[Path, ...]:
    """The interpreter's installation and virtualenv, without which `python -I -m pytest` fails."""
    prefixes = (sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix)
    return tuple(sorted({Path(p).resolve() for p in prefixes}))


def missing_hint(system: str | None = None) -> str:
    system = system or platform.system()
    tool = TOOLS.get(system)
    if tool == "bwrap":
        return (
            "bwrap not found or not working; install bubblewrap (apt install bubblewrap) and "
            "allow unprivileged user namespaces"
        )
    if tool is not None:
        return (
            f"{tool} not found or not working; it ships in /usr/bin on macOS and cannot start "
            "inside another sandbox"
        )
    return f"no sandbox tool is supported on {system}"


@cache
def _works(name: str, executable: str) -> bool:
    """Whether the tool can start the interpreter and import pytest under the real profile.

    A probe of the real command, not `--version`: the tool can exist and still fail (bwrap without
    user namespaces, sandbox-exec inside another sandbox, a profile an OS update made too tight).
    """
    argv = [sys.executable, "-I", "-B", "-c", "import pytest"]
    with tempfile.TemporaryDirectory(prefix="boss_sandbox_probe_") as folder:
        cmd = Sandbox(name, executable).wrap(
            argv, writable=Path(folder).resolve(), readable=python_readable()
        )
        try:
            done = subprocess.run(
                cmd, env={"LANG": "C.UTF-8"}, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=_PROBE_TIMEOUT_S, start_new_session=True,
            )  # fmt: skip
        except (OSError, subprocess.SubprocessError):
            return False
    return done.returncode == 0


def detect(
    environ: Mapping[str, str] | None = None, *, system: str | None = None
) -> Sandbox | None:
    """The sandbox this machine can use, or None. Looks the tool up on `environ`'s PATH."""
    env = os.environ if environ is None else environ
    name = TOOLS.get(system or platform.system())
    if name is None:
        return None
    found = shutil.which(name, path=env.get("PATH", ""))
    if found is None:
        return None
    executable = os.path.abspath(found)
    return Sandbox(name, executable) if _works(name, executable) else None


def select(
    mode: SandboxMode, environ: Mapping[str, str] | None = None, *, system: str | None = None
) -> Sandbox | None:
    """The sandbox to use under `mode`: None for OFF, or for AUTO on a machine without one."""
    if mode is SandboxMode.OFF:
        return None
    found = detect(environ, system=system)
    if found is None and mode is SandboxMode.REQUIRE:
        raise SandboxUnavailable(
            f"a sandbox is required (BOSS_GATE_SANDBOX=require) but {missing_hint(system)}"
        )
    return found
