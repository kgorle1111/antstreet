"""Runner tests against a fake CLI, so every process path is exercised without model calls."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from uuid import uuid4

import pytest

from antstreet.errors import Outcome
from antstreet.runner import WorkspaceError, _stop, deferred_sigint, run_slice
from antstreet.worker import SCHEMA_TOOL, WORKER_TOOLS, IsolationError, SliceSpec

INIT = {
    "type": "system",
    "subtype": "init",
    "tools": [*WORKER_TOOLS, SCHEMA_TOOL],
    "mcp_servers": [],
    "permissionMode": "dontAsk",
    "claude_code_version": "2.1.285",
    "session_id": "s-1",
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.0054,
    "modelUsage": {"m": {"inputTokens": 5, "outputTokens": 7, "cacheReadInputTokens": 9}},
    "structured_output": {"status": "done", "reason": "made hello.py"},
    "session_id": "s-1",
}

FAKE_CLI = f"""#!{sys.executable}
import json, os, signal, subprocess, sys, time
mode = os.environ["FAKE_MODE"]
say = lambda e: print(json.dumps(e), flush=True)
init = json.loads(os.environ["FAKE_INIT"])
def spawn_child():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    open(os.environ["FAKE_CHILD_PID"], "w").write(str(child.pid))
if mode == "unisolated":
    spawn_child()  # before any output, so the test can prove the refusal also kills it
    say({{"type": "system", "subtype": "hook_started"}})
say(init)
if mode in ("ok", "leaky"):
    if mode == "leaky":
        leak = "key sk-ant-api03-" + "x" * 30 + " and " + os.environ["ANTHROPIC_API_KEY"]
        say({{"type": "assistant", "note": leak}})
        print("stderr has sk-ant-api03-" + "y" * 30, file=sys.stderr, flush=True)
    say(json.loads(os.environ["FAKE_RESULT"]))
elif mode == "graceful":
    # Like the real CLI: SIGINT ends the turn and still reports the run's totals.
    def finish(*_):
        say(json.loads(os.environ["FAKE_RESULT"]))
        sys.exit(0)
    signal.signal(signal.SIGINT, finish)
    time.sleep(120)
elif mode == "suicide":
    os.kill(os.getpid(), signal.SIGKILL)
elif mode in ("hang", "stubborn", "unisolated"):
    if mode == "stubborn":
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode != "unisolated":
        spawn_child()
    time.sleep(120)
"""


@pytest.fixture
def fake(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    ws = tmp_path / "ws"
    ws.mkdir()
    child_pid = tmp_path / "child.pid"

    def run(mode, *, timeout_s=10.0, init=INIT, stop=None, **extra_env):
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "FAKE_MODE": mode,
            "FAKE_INIT": json.dumps(init),
            "FAKE_RESULT": json.dumps(RESULT),
            "FAKE_CHILD_PID": str(child_pid),
            **extra_env,
        }
        spec = SliceSpec(
            session_id=uuid4(), resume=False, prompt="Do it.", model="haiku", cap_micros=100_000
        )
        return run_slice(
            spec,
            ws,
            tmp_path / "logs" / "w1.jsonl",
            env=env,
            timeout_s=timeout_s,
            grace_s=0.5,
            executable=str(cli),
            stop=stop,
        )

    run.child_pid = child_pid
    run.workspace = ws
    return run


def assert_dead(pid_file):
    pid = int(pid_file.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_normal_slice_is_metered_and_logged(fake):
    run = fake("ok")
    assert run.outcome is Outcome.COMPLETED
    assert run.exit_code == 0
    assert run.usage.cost_micros == 5400
    assert run.usage.tokens_in == 5
    assert run.status == {"status": "done", "reason": "made hello.py"}
    assert run.session_id == "s-1"
    assert len(run.log_path.read_text().splitlines()) == 2


def test_process_killed_mid_run_is_a_crash(fake):
    run = fake("suicide")
    assert run.outcome is Outcome.CRASHED
    assert run.usage.cost_micros is None


# The fake must start Python and arm itself (handlers, child) before the deadline, which runs from
# the launch. 1.5 s was enough alone and not on a runner busy with parallel workers.
ARM_S = 8.0


def test_timeout_stops_the_worker_and_its_children(fake):
    start = time.monotonic()
    run = fake("hang", timeout_s=ARM_S)
    assert run.outcome is Outcome.TIMEOUT
    assert time.monotonic() - start < 60  # not the 120 s the fake sleeps
    assert_dead(fake.child_pid)


def test_worker_ignoring_sigint_and_sigterm_is_still_killed(fake):
    run = fake("stubborn", timeout_s=ARM_S)
    assert run.outcome is Outcome.TIMEOUT
    assert run.exit_code == -9
    assert_dead(fake.child_pid)


def test_unisolated_worker_is_stopped_and_refused(fake):
    start = time.monotonic()
    with pytest.raises(IsolationError, match="hook event"):
        fake("unisolated", timeout_s=30)
    assert time.monotonic() - start < 10
    assert_dead(fake.child_pid)


def test_wrong_tools_are_refused(fake):
    with pytest.raises(IsolationError, match="Bash"):
        fake("hang", init=INIT | {"tools": [*INIT["tools"], "Bash"]})


def test_log_and_stderr_are_redacted(fake):
    secret = "plain-looking-secret-value-123"
    run = fake("leaky", ANTHROPIC_API_KEY=secret)
    log = run.log_path.read_text()
    assert "sk-ant-api03-" not in log
    assert secret not in log
    assert "[REDACTED]" in log
    assert "sk-ant-api03-" not in run.stderr_tail


@pytest.mark.parametrize("planted", [".claude", ".mcp.json"])
def test_planted_agent_config_blocks_the_launch(fake, planted):
    target = fake.workspace / planted
    target.mkdir() if planted == ".claude" else target.write_text("{}")
    with pytest.raises(WorkspaceError, match="agent configuration"):
        fake("ok")


def test_timeout_interrupts_first_so_the_slice_cost_is_still_recorded(fake):
    run = fake("graceful", timeout_s=ARM_S)
    assert run.outcome is Outcome.TIMEOUT
    assert run.usage.cost_micros == 5400


def stop_once(path, stop):
    """Set `stop` from another thread as soon as `path` exists: the fake worker is then running."""

    def watch():
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (path.exists() and path.stat().st_size):
            time.sleep(0.02)
        stop.set()

    threading.Thread(target=watch, daemon=True).start()


def test_a_slice_can_be_stopped_from_another_thread_and_its_cost_is_still_read(fake, tmp_path):
    # Parallel slices run in threads; Ctrl-C reaches only the main one, which sets this event.
    stop = threading.Event()
    stop_once(tmp_path / "logs" / "w1.jsonl", stop)  # the init line is logged: it is running
    start = time.monotonic()
    run = fake("graceful", timeout_s=120.0, stop=stop)
    assert time.monotonic() - start < 60
    assert run.outcome is Outcome.TIMEOUT
    assert run.usage.cost_micros == 5400  # interrupted first, so the final result was printed


def ctrl_c_once(path):
    """Send this process a real SIGINT as soon as `path` has content: the fake worker is running."""

    def watch():
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (path.exists() and path.stat().st_size):
            time.sleep(0.02)
        os.kill(os.getpid(), signal.SIGINT)

    threading.Thread(target=watch, daemon=True).start()


@pytest.mark.sigint
def test_ctrl_c_stops_the_worker_first_and_raises_where_no_lock_is_held(fake, tmp_path):
    # Raised mid-queue.get, KeyboardInterrupt left a lock released twice ("release unlocked lock")
    # or held (under coverage, a hang). Deferred, it is raised by deferred_sigint, after the stop.
    stop = threading.Event()
    ctrl_c_once(tmp_path / "logs" / "w1.jsonl")
    with pytest.raises(KeyboardInterrupt) as raised:
        fake("graceful", timeout_s=120.0, stop=stop)
    assert traceback.extract_tb(raised.value.__traceback__)[-1].name == "deferred_sigint"
    assert stop.is_set()  # parallel slices sharing this event stop too
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


@pytest.mark.sigint
def test_ctrl_c_in_a_deferred_block_is_raised_only_when_the_block_ends():
    stop, after = threading.Event(), []
    with pytest.raises(KeyboardInterrupt), deferred_sigint(stop):
        os.kill(os.getpid(), signal.SIGINT)
        time.sleep(0.2)  # a KeyboardInterrupt raised here would skip the next line
        after.append(stop.is_set())
    assert after == [True]
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_deferring_ctrl_c_leaves_another_handler_and_other_threads_alone():
    def mine(*_):
        pass

    previous = signal.signal(signal.SIGINT, mine)
    try:
        with deferred_sigint(threading.Event()):
            assert signal.getsignal(signal.SIGINT) is mine
    finally:
        signal.signal(signal.SIGINT, previous)
    seen = []

    def in_a_thread():
        with deferred_sigint(threading.Event()):
            seen.append(signal.getsignal(signal.SIGINT))

    thread = threading.Thread(target=in_a_thread)
    thread.start()
    thread.join()
    assert seen == [signal.default_int_handler]


def test_stopping_a_hung_slice_kills_it_and_its_children(fake):
    stop = threading.Event()
    stop_once(fake.child_pid, stop)
    start = time.monotonic()
    fake("hang", timeout_s=120.0, stop=stop)
    assert time.monotonic() - start < 60
    assert_dead(fake.child_pid)


def test_an_unset_stop_event_changes_nothing(fake):
    run = fake("ok", stop=threading.Event())
    assert run.outcome is Outcome.COMPLETED


def test_stopping_a_worker_that_already_exited_reaps_it_instead_of_raising():
    # An exited, unreaped group leader is a zombie; macOS refuses killpg on its group with EPERM.
    proc = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    time.sleep(1.0)  # let it exit; nothing reaps it until _stop does
    _stop(proc, grace_s=1.0)
    assert proc.returncode == 0
