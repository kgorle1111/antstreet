"""The gate: the only component allowed to say a check passed.

Each check runs in its own pytest process against a fresh copy of the workspace. The worker's
files can execute during a check, so the gate never trusts the exit code alone: a check passes
only when pytest exits 0 *and* its JUnit report shows at least one test, all of them passing.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DEFAULT_TIMEOUT_S = 60.0
OUTPUT_TAIL_CHARS = 4000
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc", ".git")
# kn: in-process verdicts are forgeable by deliberately adversarial code; the benchmark's hidden
# checks measure that gap. Container isolation is parked until untrusted ideas are supported.
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

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASSED


def run_gate(
    workspace: Path,
    checks_dir: Path,
    checks: Sequence[Check],
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[CheckResult]:
    """Run every check against a fresh copy of `workspace`. The original is never modified."""
    if importlib.util.find_spec("pytest") is None:
        raise GateError("pytest is not installed in the environment running boss")
    workspace, checks_dir = Path(workspace).resolve(), Path(checks_dir).resolve()
    if not workspace.is_dir():
        raise GateError(f"workspace {workspace} does not exist")
    sources = [_check_source(checks_dir, c) for c in checks]
    return [_run_one(workspace, c, src, timeout_s) for c, src in zip(checks, sources, strict=True)]


def _check_source(checks_dir: Path, check: Check) -> Path:
    src = (checks_dir / check.file).resolve()
    if not src.is_relative_to(checks_dir):
        raise GateError(f"check {check.id} points outside the checks directory: {check.file}")
    if not src.is_file():
        raise GateError(f"check {check.id} file not found: {check.file}")
    return src


def _run_one(workspace: Path, check: Check, src: Path, timeout_s: float) -> CheckResult:
    with tempfile.TemporaryDirectory(prefix="boss_gate_") as tmp_name:
        tmp = Path(tmp_name)
        shutil.copytree(workspace, tmp / "ws", symlinks=True, ignore=_COPY_IGNORE)
        (tmp / "checks").mkdir()
        target = tmp / "checks" / src.name
        shutil.copy2(src, target)
        (tmp / "pytest.ini").write_text(_INI)
        (tmp / "home").mkdir()
        report = tmp / "report.xml"
        cmd = [
            sys.executable, "-I", "-B", "-m", "pytest", str(target),
            "-c", str(tmp / "pytest.ini"), "--rootdir", str(tmp), "-p", "no:cacheprovider",
            f"--junitxml={report}", "-q", "--no-header",
        ]  # fmt: skip
        start = time.monotonic()
        exit_code, output, timed_out = _run_bounded(cmd, tmp / "ws", _env(tmp), timeout_s)
        duration = time.monotonic() - start
        tail = output[-OUTPUT_TAIL_CHARS:]
        if timed_out:
            return CheckResult(check.id, CheckStatus.TIMEOUT, None, f"exceeded {timeout_s}s",
                               tail, duration)  # fmt: skip
        ok, detail = _verdict(exit_code, report)
        status = CheckStatus.PASSED if ok else CheckStatus.FAILED
        return CheckResult(check.id, status, exit_code, detail, tail, duration)


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
        cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True,
    )  # fmt: skip
    try:
        out, _ = proc.communicate(timeout=timeout_s)
        return proc.returncode, out, False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        return None, out, True


def _verdict(exit_code: int | None, report: Path) -> tuple[bool, str]:
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
    return True, f"{counts['tests']} passed"
