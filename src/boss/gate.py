"""The gate: the only component allowed to say a check passed.

Each check runs in its own pytest process against a fresh copy of the workspace. The worker's
files can execute during a check, so the gate never trusts the exit code alone: a check passes
only when pytest exits 0, its JUnit report shows at least one test and all of them passing, *and*
a plugin the gate loaded (`boss._gate_plugin`) left a proof signed with a per-run nonce that says
every collected test really passed, with the same count as the report. Where the platform has one,
the process runs inside an OS sandbox (`boss.sandbox`).
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from boss.sandbox import Sandbox, SandboxMode, SandboxUnavailable, python_readable, select

DEFAULT_TIMEOUT_S = 60.0
SANDBOX_ENV = "BOSS_GATE_SANDBOX"
OUTPUT_TAIL_CHARS = 4000
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".git")
# kn: in-process verdicts are forgeable by deliberately adversarial code that reads the plugin's
# nonce from the check's own process (gc, sys.modules); closing that needs the verdict read from
# outside the process that runs worker code (a container or an out-of-process runner), parked until
# untrusted ideas are supported.
_PLUGIN_SOURCE = Path(__file__).with_name("_gate_plugin.py")
_PROOF_MAX_BYTES = 512  # a proof is "<n> <n> <64 hex>"; never read more of a file the check wrote
_BOOTSTRAP = (  # not `-m pytest`: the plugin folder joins sys.path, the workspace still does not
    "import sys; sys.path.insert(0, sys.argv[1]); import pytest\n"
    "sys.exit(pytest.main(sys.argv[2:]))"
)
_INI = "[pytest]\npythonpath = ws\n"


class GateError(Exception):
    """The gate itself cannot run. Never the worker's fault."""


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    file: str  # relative to the checks directory


@dataclass(frozen=True, slots=True)
class CheckResult:
    check_id: str
    status: CheckStatus
    exit_code: int | None
    detail: str
    output_tail: str
    duration_s: float
    sandboxed: bool = False  # ran inside an OS sandbox; False also means the sandbox was off

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASSED


def sandbox_mode(environ: Mapping[str, str]) -> SandboxMode:
    """The mode `BOSS_GATE_SANDBOX` asks for; AUTO when it is unset."""
    raw = environ.get(SANDBOX_ENV)
    if raw is None:
        return SandboxMode.AUTO
    try:
        return SandboxMode(raw.strip().lower())
    except ValueError:
        allowed = "|".join(m.value for m in SandboxMode)
        raise GateError(f"{SANDBOX_ENV}={raw!r} is not one of {allowed}") from None


def run_gate(
    workspace: Path,
    checks_dir: Path,
    checks: Sequence[Check],
    timeout_s: float = DEFAULT_TIMEOUT_S,
    sandbox: SandboxMode | None = None,
) -> list[CheckResult]:
    """Run every check against a fresh copy of `workspace`. The original is never modified.

    `sandbox=None` defers to `BOSS_GATE_SANDBOX`, then to AUTO: the one place the variable is read.
    """
    mode = sandbox_mode(os.environ) if sandbox is None else sandbox
    if importlib.util.find_spec("pytest") is None:
        raise GateError("pytest is not installed in the environment running boss")
    workspace, checks_dir = Path(workspace).resolve(), Path(checks_dir).resolve()
    if not workspace.is_dir():
        raise GateError(f"workspace {workspace} does not exist")
    sources = [_check_source(checks_dir, c) for c in checks]
    try:
        tool = select(mode) if checks else None
    except SandboxUnavailable as exc:
        raise GateError(str(exc)) from exc
    runs = zip(checks, sources, strict=True)
    return [_run_one(workspace, c, src, timeout_s, tool) for c, src in runs]


def _check_source(checks_dir: Path, check: Check) -> Path:
    src = (checks_dir / check.file).resolve()
    if not src.is_relative_to(checks_dir):
        raise GateError(f"check {check.id} points outside the checks directory: {check.file}")
    if not src.is_file():
        raise GateError(f"check {check.id} file not found: {check.file}")
    return src


def _run_one(
    workspace: Path, check: Check, src: Path, timeout_s: float, tool: Sandbox | None
) -> CheckResult:
    with tempfile.TemporaryDirectory(prefix="boss_gate_") as tmp_name:
        tmp = Path(tmp_name)
        shutil.copytree(workspace, tmp / "ws", symlinks=True, ignore=_COPY_IGNORE)
        (tmp / "checks").mkdir()
        target = tmp / "checks" / src.name
        shutil.copy2(src, target)
        (tmp / "pytest.ini").write_text(_INI)
        (tmp / "home").mkdir()
        report = tmp / "report.xml"
        nonce, plugin = secrets.token_hex(32), f"_boss_gate_{secrets.token_hex(8)}"
        proof = tmp / f"proof_{secrets.token_hex(8)}"
        (tmp / "plugin").mkdir()
        (tmp / "plugin" / f"{plugin}.py").write_text(
            _PLUGIN_SOURCE.read_text().replace("@NONCE@", nonce).replace("@PROOF@", str(proof))
        )
        cmd = [
            sys.executable, "-I", "-B", "-c", _BOOTSTRAP, str(tmp / "plugin"), str(target),
            "-c", str(tmp / "pytest.ini"), "--rootdir", str(tmp), "-p", "no:cacheprovider",
            "-p", plugin, f"--junitxml={report}", "-q", "--no-header",
        ]  # fmt: skip
        if tool is not None:
            cmd = tool.wrap(cmd, writable=tmp.resolve(), readable=python_readable())
        start = time.monotonic()
        exit_code, output, timed_out = _run_bounded(cmd, tmp / "ws", _env(tmp), timeout_s)
        duration = time.monotonic() - start
        tail = output[-OUTPUT_TAIL_CHARS:]
        sandboxed = tool is not None
        if timed_out:
            detail = f"exceeded {timeout_s}s"
            return CheckResult(
                check.id, CheckStatus.TIMEOUT, None, detail, tail, duration, sandboxed
            )
        ok, detail = _verdict(exit_code, report, proof, nonce)
        status = CheckStatus.PASSED if ok else CheckStatus.FAILED
        return CheckResult(check.id, status, exit_code, detail, tail, duration, sandboxed)


def _env(tmp: Path) -> dict[str, str]:
    """Allowlisted environment: nothing from the caller's secrets or config reaches the check."""
    return {
        "PATH": os.pathsep.join([str(Path(sys.executable).parent), "/usr/bin", "/bin"]),
        "HOME": str(tmp / "home"),
        "TMPDIR": str(tmp),
        "LANG": "C.UTF-8",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }


def _run_bounded(
    cmd: list[str], cwd: Path, env: dict[str, str], timeout_s: float
) -> tuple[int | None, str, bool]:
    """Run in a new process group so a timeout also kills anything the check spawned."""
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return proc.returncode, out, False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return None, out, True


def _verdict(exit_code: int | None, report: Path, proof: Path, nonce: str) -> tuple[bool, str]:
    if exit_code != 0:
        return False, f"pytest exited {exit_code}"
    if not report.is_file():
        return False, "exit 0 but no JUnit report was written"
    try:
        root = ET.parse(report).getroot()
    except ET.ParseError as exc:
        return False, f"unreadable JUnit report: {exc}"
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors")}
    counts["skipped"] = sum(int(s.get("skipped", 0)) for s in suites)
    if counts["tests"] == 0:
        return False, "no tests ran"
    not_passed = counts["failures"] + counts["errors"] + counts["skipped"]
    if not_passed:
        return False, "report shows {failures} failed, {errors} errors, {skipped} skipped".format(
            **counts
        )
    proved = _proof_count(proof, nonce)
    if proved is None:
        return False, "exit 0 but the gate's pytest plugin left no valid proof of a clean session"
    if proved != counts["tests"]:
        return False, f"report shows {counts['tests']} tests but the proof covers {proved}"
    return True, f"{counts['tests']} passed"


def _proof_count(proof: Path, nonce: str) -> int | None:
    """The test count the plugin signed, or None if the file is missing, forged or malformed."""
    try:
        if proof.is_symlink() or not proof.is_file():
            return None
        with proof.open("rb") as fh:
            parts = fh.read(_PROOF_MAX_BYTES).decode("ascii").split(" ")
        total, passed, mac = parts
        expected = hmac.new(nonce.encode(), f"{total}:{passed}".encode(), hashlib.sha256)
        if total != passed or not hmac.compare_digest(mac, expected.hexdigest()):
            return None
        return int(total)
    except (OSError, ValueError):
        return None
