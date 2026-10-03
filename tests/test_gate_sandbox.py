"""What the OS sandbox denies and what it does not, tested by attempting each act from a check.

Skipped where `detect()` finds no working tool. Each attack runs twice where that is safe: with
the sandbox OFF (it succeeds, so the test is not vacuous) and REQUIRE (it is denied). Attacks
target paths the test made under `tmp_path` and a fake home; the real home is never touched.
Tests marked `mac_only` pin the seatbelt profile's deny-by-default reach; the bwrap argv has not
been run (see docs/SANDBOX.md).
"""

import contextlib
import os
import platform
import re
import select
import signal
import socket
import subprocess
import tempfile
import textwrap
import time
import uuid
from pathlib import Path

import pytest
from gate_forgers import NONCE_READER
from sandbox_support import working_sandbox

from boss.gate import Check, CheckStatus, run_gate
from boss.sandbox import SandboxMode, python_readable
from boss.termsheet import CheckSpec, Round, Task, TermSheet, validate

TOOL = working_sandbox()
requires_sandbox = pytest.mark.skipif(TOOL is None, reason="no working OS sandbox on this machine")
mac_only = pytest.mark.skipif(
    TOOL is None or TOOL.name != "sandbox-exec", reason="pins the macOS seatbelt profile"
)
BWRAP = TOOL is not None and TOOL.name == "bwrap"
# Outside the gate's folder a check never gets "Operation not permitted" on Linux: bwrap hides the
# whole directory (`--tmpfs /tmp`, `/home`), so the path is simply not there.
NOT_ALLOWED = r"PermissionError|FileNotFoundError"
ON, OFF = SandboxMode.REQUIRE, SandboxMode.OFF

RIGHT = "def reverse(s):\n    return s[::-1]\n"
WRONG = "def reverse(s):\n    return s\n"
HONEST = "from rev import reverse\n\ndef test_reverse():\n    assert reverse('ab') == 'ba'\n"
PROBE = """\
import os, shutil, socket, subprocess, sys

def test_probe():
    try:
{body}
    except OSError as exc:
        outcome = "denied:" + type(exc).__name__
    else:
        outcome = "allowed"
    raise AssertionError("OUTCOME=" + outcome)
"""
# Rewrites the gate's own JUnit report as a clean pass, from the path in argv (T12).
FORGER = (
    "import atexit, os, sys\n"
    "def forge():\n"
    "    path = next(a for a in sys.argv if a.startswith('--junitxml=')).split('=', 1)[1]\n"
    "    with open(path, 'w') as fh:\n"
    '        fh.write(\'<testsuite tests="1" failures="0" errors="0" skipped="0"/>\')\n'
    "    os._exit(0)\n"
    "atexit.register(forge)\n"
)


def gate(tmp_path: Path, check: str, product: str, mode: SandboxMode, timeout_s: float = 30.0):
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    ws.mkdir(exist_ok=True)
    checks.mkdir(exist_ok=True)
    (checks / "test_c01.py").write_text(check)
    (ws / "rev.py").write_text(product)
    [result] = run_gate(
        ws, checks, [Check("c01", "test_c01.py")], timeout_s=timeout_s, sandbox=mode
    )
    return result


def attempt(tmp_path: Path, body: str, mode: SandboxMode) -> str:
    """'allowed' or 'denied:<ErrorName>' for `body`, run as a check under `mode`."""
    result = gate(tmp_path, PROBE.format(body=textwrap.indent(body, " " * 8)), "", mode)
    assert result.sandboxed is (mode is not OFF), result.output_tail
    found = re.search(r"OUTCOME=([\w:]+)", result.output_tail)
    assert found, f"the probe did not report: {result.output_tail}"
    return found.group(1)


def denied(outcome: str) -> bool:
    return outcome.startswith("denied:")


def test_a_seatbelt_tool_that_works_means_our_profile_lets_python_start():
    """Without this, a profile an OS update made too tight would skip every test above."""
    tool = Path("/usr/bin/sandbox-exec")
    if platform.system() != "Darwin" or not tool.exists():
        pytest.skip("not macOS")
    trivial = subprocess.run([tool, "-p", "(version 1)(allow default)", "/usr/bin/true"])
    if trivial.returncode != 0:
        pytest.skip("sandbox-exec cannot run here (already inside a sandbox?)")
    assert TOOL is not None and TOOL.name == "sandbox-exec"


# --- (a) honest checks are unaffected --------------------------------------------------------


@requires_sandbox
def test_an_honest_passing_check_still_passes_and_says_it_was_sandboxed(tmp_path):
    result = gate(tmp_path, HONEST, RIGHT, ON)
    assert result.status is CheckStatus.PASSED, result.output_tail
    assert result.detail == "1 passed" and result.sandboxed is True


@requires_sandbox
def test_an_honest_failing_check_still_fails_on_its_assertion_not_on_the_sandbox(tmp_path):
    result = gate(tmp_path, HONEST, WRONG, ON)
    assert result.status is CheckStatus.FAILED and result.sandboxed is True
    assert result.detail == "pytest exited 1"
    assert "assert 'ab' == 'ba'" in result.output_tail
    assert "Operation not permitted" not in result.output_tail


HONEST_TOOLKIT = """\
import asyncio, concurrent.futures, datetime, getpass, locale, multiprocessing, os, sqlite3
import subprocess, sys, tempfile, threading, zoneinfo

def test_what_ordinary_code_needs():
    assert asyncio.run(asyncio.sleep(0, 3)) == 3
    threading.Thread(target=lambda: None).start()
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        assert list(pool.map(abs, [-1])) == [1]
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        assert pool.map(abs, [-2]) == [2]
    sqlite3.connect(":memory:").execute("select 1")
    zoneinfo.ZoneInfo("America/New_York")
    assert locale.getpreferredencoding() == "UTF-8"
    assert getpass.getuser()
    assert tempfile.mkdtemp().startswith(os.environ["TMPDIR"])
    assert len(os.urandom(4)) == 4
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    child.kill()
    assert child.wait() == -9
    said = subprocess.run([sys.executable, "-c", "print(6*7)"], capture_output=True)
    assert said.stdout == b"42\\n"
    assert os.path.isfile(os.__file__) and open(os.__file__).read()
"""


@requires_sandbox
def test_ordinary_test_code_keeps_working(tmp_path):
    result = gate(tmp_path, HONEST_TOOLKIT, "", ON)
    assert result.status is CheckStatus.PASSED, result.output_tail


@requires_sandbox
def test_the_local_time_zone_survives_the_sandbox(tmp_path):
    zone = (
        "import datetime\n"
        "def test_tz():\n"
        "    raise AssertionError('TZ=' + datetime.datetime.now().astimezone().tzname())\n"
    )
    seen = {}
    for mode in (ON, OFF):
        tail = gate(tmp_path, zone, "", mode).output_tail
        seen[mode] = re.search(r"TZ=(\w+)", tail)
        assert seen[mode], tail
    assert seen[ON].group(1) == seen[OFF].group(1)  # without the zone database it would be UTC


BUILT_IN_ZONES = Path("/usr/share/zoneinfo.default")


@requires_sandbox
@pytest.mark.skipif(not BUILT_IN_ZONES.is_dir(), reason="no built-in time zone copy here")
def test_the_built_in_time_zone_copy_is_readable_for_a_mac_with_no_downloaded_update(tmp_path):
    # /usr/share/zoneinfo resolves into /private/var/db/timezone only once macOS has downloaded
    # a time zone update; before that it resolves here, as on a fresh CI runner.
    check = (
        "import zoneinfo\n"
        "def test_zone():\n"
        f"    with open('{BUILT_IN_ZONES}/America/New_York', 'rb') as fh:\n"
        "        assert zoneinfo.ZoneInfo.from_file(fh).utcoffset(None) is None\n"
    )
    result = gate(tmp_path, check, "", ON)
    assert result.status is CheckStatus.PASSED, result.output_tail


# --- (b) no network --------------------------------------------------------------------------


@requires_sandbox
def test_a_tcp_connection_to_a_local_listener_is_denied_and_never_arrives(tmp_path):
    with contextlib.closing(socket.socket()) as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        body = f"socket.create_connection(('127.0.0.1', {server.getsockname()[1]}), timeout=3)"
        assert attempt(tmp_path, body, OFF) == "allowed"
        assert select.select([server], [], [], 1)[0], "the unsandboxed connection did not arrive"
        server.accept()
        assert denied(attempt(tmp_path, body, ON))
        assert not select.select([server], [], [], 0.5)[0], "a sandboxed connection got through"


@requires_sandbox
def test_a_udp_datagram_to_a_local_receiver_is_denied_and_never_arrives(tmp_path):
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as receiver:
        receiver.bind(("127.0.0.1", 0))
        body = (
            "s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)\n"
            f"s.sendto(b'x', ('127.0.0.1', {receiver.getsockname()[1]}))"
        )
        assert attempt(tmp_path, body, OFF) == "allowed"
        assert select.select([receiver], [], [], 1)[0]
        receiver.recv(10)
        # bwrap gives the check a private loopback of its own: the send succeeds into nothing.
        assert denied(attempt(tmp_path, body, ON)) or BWRAP
        assert not select.select([receiver], [], [], 0.5)[0], "a sandboxed datagram got through"


@requires_sandbox
def test_a_unix_socket_the_user_could_reach_is_denied(tmp_path):
    folder = Path(tempfile.mkdtemp(prefix="bs", dir="/tmp"))  # sun_path is short
    path = str(folder / "s")
    body = f"s = socket.socket(socket.AF_UNIX)\ns.connect({path!r})"
    with contextlib.closing(socket.socket(socket.AF_UNIX)) as server:
        server.bind(path)
        server.listen()
        assert attempt(tmp_path, body, OFF) == "allowed"
        assert denied(attempt(tmp_path, body, ON))
    (folder / "s").unlink()
    folder.rmdir()


@requires_sandbox
def test_opening_a_listening_socket_is_denied(tmp_path):
    if BWRAP:
        pytest.skip(
            "--unshare-net gives the check a loopback of its own; nothing outside reaches it"
        )
    body = "s = socket.socket()\ns.bind(('127.0.0.1', 0))\ns.listen()"
    assert attempt(tmp_path, body, OFF) == "allowed"
    assert denied(attempt(tmp_path, body, ON))


# --- (c) writes only inside the gate's folder ------------------------------------------------


@requires_sandbox
def test_a_file_cannot_be_written_outside_the_gates_folder(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    body = f"open({str(outside / 'planted')!r}, 'w').write('x')"
    assert attempt(tmp_path, body, OFF) == "allowed"
    (outside / "planted").unlink()
    assert denied(attempt(tmp_path, body, ON))
    assert not (outside / "planted").exists()


@requires_sandbox
def test_worker_code_imported_by_the_check_cannot_write_outside_the_gates_folder(tmp_path):
    """The sandboxed counterpart of test_safety's host-access test, which runs with it OFF."""
    outside = tmp_path / "written-outside-the-gate-copy"
    code = f"open({str(outside)!r}, 'w').write('x')\n" + WRONG
    result = gate(tmp_path, HONEST, code, ON)
    assert result.status is CheckStatus.FAILED and result.sandboxed is True
    assert re.search(NOT_ALLOWED, result.output_tail), result.output_tail
    assert not outside.exists()


@requires_sandbox
def test_check_code_run_during_validation_cannot_write_outside_the_gates_folder(
    tmp_path, monkeypatch
):
    """The sandboxed counterpart of the validation-before-approval accepted risk (T14)."""
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "require")
    ran = tmp_path / "ran-before-approval"
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(
        f"open({str(ran)!r}, 'w').write('x')\ndef test_x():\n    assert False\n"
    )
    sheet = TermSheet(
        idea="Reverse a string.",
        budget_micros=500_000,
        rounds=(Round(1, 500_000, 1),),
        checks=(CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
        tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
    )
    validate(sheet, checks)  # sound sheet; the check fails on an empty workspace: no problems
    assert not ran.exists()


WRITE_OPS = {
    "create": "open(D + '/new', 'w').write('x')",
    "overwrite": "open(D + '/keep', 'w').write('x')",
    "append": "open(D + '/keep', 'a').write('x')",
    "delete": "os.unlink(D + '/keep')",
    "rename": "os.rename(D + '/keep', D + '/moved')",
    "mkdir": "os.mkdir(D + '/sub')",
    "symlink": "os.symlink('/etc', D + '/link')",
    "truncate": "os.truncate(D + '/keep', 0)",
    "chmod": "os.chmod(D + '/keep', 0o777)",
}


@requires_sandbox
@pytest.mark.parametrize("op", WRITE_OPS)
def test_no_way_of_changing_the_outside_world_works(tmp_path, op):
    outside = tmp_path / "outside"
    outside.mkdir()
    keep = outside / "keep"
    keep.write_text("original")
    body = f"D = {str(outside)!r}\n{WRITE_OPS[op]}"
    assert denied(attempt(tmp_path, body, ON)), op
    assert keep.read_text() == "original" and sorted(p.name for p in outside.iterdir()) == ["keep"]
    assert attempt(tmp_path, body, OFF) == "allowed", op


@requires_sandbox
def test_the_copy_of_the_workspace_and_the_temp_folder_are_writable(tmp_path):
    body = (
        "open('scratch.txt', 'w').write('x')\n"
        "os.mkdir('made')\n"
        "open(os.path.join(os.environ['TMPDIR'], 'more.txt'), 'w').write('x')\n"
        "open(os.path.join(os.environ['HOME'], '.cache-file'), 'w').write('x')"
    )
    assert attempt(tmp_path, body, ON) == "allowed"


@requires_sandbox
def test_the_real_workspace_is_unreadable_and_unwritable_from_the_check(tmp_path):
    marker = tmp_path / "ws" / "planted"
    body = f"open({str(marker)!r}, 'w').write('x')"
    assert denied(attempt(tmp_path, body, ON)) and not marker.exists()
    assert denied(attempt(tmp_path, f"open({str(tmp_path / 'ws' / 'rev.py')!r}).read()", ON))


# --- (d) reads only what Python needs --------------------------------------------------------


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "fake-home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "id_test").write_text("not a real key")
    (home / ".claude").mkdir()
    (home / ".claude" / "credentials.json").write_text('{"token": "not real"}')
    return home


@requires_sandbox
@pytest.mark.parametrize("secret", [".ssh/id_test", ".claude/credentials.json"])
def test_a_secret_outside_the_allowed_paths_cannot_be_read(tmp_path, fake_home, secret):
    body = f"open({str(fake_home / secret)!r}).read()"
    assert attempt(tmp_path, body, OFF) == "allowed"
    assert denied(attempt(tmp_path, body, ON))


@requires_sandbox
def test_a_folder_of_secrets_cannot_be_listed(tmp_path, fake_home):
    body = f"os.listdir({str(fake_home / '.ssh')!r})"
    assert attempt(tmp_path, body, OFF) == "allowed"
    assert denied(attempt(tmp_path, body, ON))


@requires_sandbox
def test_the_interpreter_and_its_libraries_are_readable_but_not_their_neighbours(tmp_path):
    readable = python_readable()[0]
    assert attempt(tmp_path, f"os.listdir({str(readable)!r})", ON) == "allowed"
    if BWRAP:  # `--ro-bind / /` leaves every neighbour outside /home, /root, /tmp, /run readable
        return
    beside = readable.parent
    assert attempt(tmp_path, f"os.listdir({str(beside)!r})", OFF) == "allowed"
    assert denied(attempt(tmp_path, f"os.listdir({str(beside)!r})", ON))


@requires_sandbox
def test_a_child_process_is_confined_like_its_parent(tmp_path, fake_home):
    secret = fake_home / ".ssh" / "id_test"
    body = (
        f"r = subprocess.run(['/bin/cat', {str(secret)!r}], capture_output=True)\n"
        "if r.returncode != 0:\n    raise PermissionError(r.stderr)"
    )
    assert attempt(tmp_path, body, OFF) == "allowed"
    assert denied(attempt(tmp_path, body, ON))


@mac_only
def test_files_readable_by_every_user_are_not_readable_either(tmp_path):
    body = "open('/etc/hosts').read()"
    assert attempt(tmp_path, body, OFF) == "allowed"
    assert denied(attempt(tmp_path, body, ON))


@mac_only
def test_the_names_of_files_are_still_visible_to_stat(tmp_path, fake_home):
    """Not a control: pins the known leak that metadata is readable everywhere (T13)."""
    body = f"os.stat({str(fake_home / '.ssh' / 'id_test')!r})"
    assert attempt(tmp_path, body, ON) == "allowed"


# --- system services and other processes (macOS) ----------------------------------------------


def run_command(tmp_path: Path, argv: list[str], mode: SandboxMode) -> tuple[int, str]:
    """Exit code and stderr of `argv` run from a check under `mode`."""
    body = (
        f"r = subprocess.run({argv!r}, capture_output=True, text=True, timeout=20)\n"
        "raise RuntimeError('RC=%d|%s' % (r.returncode, r.stderr.strip()[:200]))"
    )
    tail = gate(tmp_path, PROBE.format(body=textwrap.indent(body, " " * 8)), "", mode).output_tail
    found = re.search(r"RC=(\d+)\|(.*)", tail)
    assert found, tail
    return int(found.group(1)), found.group(2)


@mac_only
def test_the_keychain_the_clipboard_and_launch_services_are_out_of_reach(tmp_path):
    lookup = ["/usr/bin/security", "find-generic-password", "-s", f"boss-probe-{uuid.uuid4().hex}"]
    assert "could not be found" in run_command(tmp_path, lookup, OFF)[1]  # the daemon answered
    assert "could not be found" not in run_command(tmp_path, lookup, ON)[1]  # it never did
    assert run_command(tmp_path, ["/usr/bin/pbpaste"], OFF)[0] == 0
    assert run_command(tmp_path, ["/usr/bin/pbpaste"], ON)[0] != 0
    assert run_command(tmp_path, ["/usr/bin/open", "-g", "-a", "Finder"], ON)[0] != 0
    assert run_command(tmp_path, ["/usr/bin/osascript", "-e", "return 1"], ON)[0] != 0


@mac_only
def test_the_check_cannot_signal_the_process_that_runs_the_gate(tmp_path):
    body = f"os.kill({os.getpid()}, 0)"
    assert attempt(tmp_path, body, OFF) == "allowed"
    assert denied(attempt(tmp_path, body, ON))


@mac_only
def test_the_sandbox_cannot_be_reapplied_or_loosened_from_inside(tmp_path):
    assert TOOL is not None
    inner = TOOL.wrap(["/usr/bin/true"], writable=tmp_path.resolve(), readable=[])
    body = (
        f"if subprocess.run({inner!r}, capture_output=True).returncode:\n    raise PermissionError"
    )
    assert denied(attempt(tmp_path, body, ON))


# --- hostile directory names ------------------------------------------------------------------

NAMES = ["sp ace", 'quo"te', "apos'trophe", "par(en)s)", "new\nline", "back\\slash", "é中",
         '"))(allow default)((']  # fmt: skip


@requires_sandbox
@pytest.mark.parametrize("name", NAMES)
def test_a_hostile_directory_name_grants_that_directory_and_nothing_else(tmp_path, name):
    granted, sibling, library = (
        tmp_path / name,
        tmp_path / f"{name}-sibling",
        tmp_path / f"{name}-r",
    )
    for folder in (granted, sibling, library):
        folder.mkdir()
    (library / "data").write_text("x")
    (sibling / "data").write_text("x")
    script = (
        'echo hi > "$1/in" && echo write-ok; echo hi > "$2/out" 2>/dev/null && echo sibling-write; '
        'cat "$3/data" > /dev/null 2>&1 && echo read-ok; cat "$2/data" > /dev/null 2>&1 && '
        "echo sibling-read"
    )
    assert TOOL is not None
    cmd = TOOL.wrap(
        ["/bin/sh", "-c", script, "sh", str(granted), str(sibling), str(library)],
        writable=granted.resolve(),
        readable=[library.resolve()],
    )
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert done.stdout.split() == ["write-ok", "read-ok"], done.stderr
    assert not (sibling / "out").exists()


# --- (e) the forged report: not solved, and not made worse -----------------------------------


@requires_sandbox
def test_a_report_rewritten_from_inside_the_sandbox_is_not_a_pass(tmp_path):
    result = gate(tmp_path, HONEST, FORGER + WRONG, ON)
    assert result.sandboxed is True
    assert result.status is CheckStatus.FAILED
    assert "no valid proof" in result.detail


@requires_sandbox
def test_accepted_risk_code_aimed_at_the_gate_still_forges_a_pass_inside_the_sandbox(tmp_path):
    # The plugin's nonce is in the one process the sandbox confines the check to (T12).
    result = gate(tmp_path, HONEST, NONCE_READER + WRONG, ON)
    assert result.sandboxed is True
    assert result.status is CheckStatus.PASSED
    assert result.detail == "1 passed"


# --- (f) timeouts and process groups ---------------------------------------------------------


def children_with(marker: str) -> list[int]:
    done = subprocess.run(["/usr/bin/pgrep", "-f", marker], capture_output=True, text=True)
    return [int(pid) for pid in done.stdout.split()]


def spawn_sleeper(marker: str, *, detached: bool) -> str:
    return (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)  # {marker}'],\n"
        f"                 start_new_session={detached})\n"
        "time.sleep(60)\n"
    )


def wait_gone(marker: str, seconds: float = 3.0) -> list[int]:
    deadline = time.monotonic() + seconds
    while (pids := children_with(marker)) and time.monotonic() < deadline:
        time.sleep(0.1)
    return pids


@requires_sandbox
def test_a_hanging_check_and_its_child_are_killed_at_the_timeout(tmp_path):
    marker = f"boss-sleeper-{uuid.uuid4().hex}"
    start = time.monotonic()
    result = gate(tmp_path, HONEST, spawn_sleeper(marker, detached=False), ON, timeout_s=3.0)
    assert result.status is CheckStatus.TIMEOUT and result.sandboxed is True
    assert time.monotonic() - start < 20
    assert wait_gone(marker) == []


@requires_sandbox
def test_accepted_risk_a_detached_child_outlives_the_timeout_inside_the_sandbox_too(tmp_path):
    marker = f"boss-detached-{uuid.uuid4().hex}"
    try:
        result = gate(tmp_path, HONEST, spawn_sleeper(marker, detached=True), ON, timeout_s=3.0)
        assert result.status is CheckStatus.TIMEOUT
        if BWRAP:
            # The group kill reaches bwrap's init, pid 1 of the check's pid namespace, and the
            # kernel then kills every process in that namespace, detached or not.
            assert wait_gone(marker) == [], "a detached child outlived the pid namespace"
            return
        survivors = children_with(marker)
        assert survivors, "the sandbox is now killing detached children: update THREAT_MODEL T05"
    finally:
        for pid in children_with(marker):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)


@requires_sandbox
@pytest.mark.parametrize(("mode", "planted"), [(OFF, True), (ON, False)], ids=["off", "on"])
def test_a_detached_child_is_confined_like_the_check_that_started_it(tmp_path, mode, planted):
    marker = f"boss-confined-{uuid.uuid4().hex}"
    outside = tmp_path / "planted-by-child"
    child = f"import time; time.sleep(1); open({str(outside)!r}, 'w').write('x')  # {marker}"
    code = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child!r}], start_new_session=True)\n"
        "time.sleep(3)\n"
    )
    try:
        gate(tmp_path, HONEST, code, mode, timeout_s=2.0)
        wait_gone(marker, seconds=5.0)
        assert outside.exists() is planted
    finally:
        for pid in children_with(marker):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
