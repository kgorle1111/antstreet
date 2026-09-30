"""Runner tests against a fake CLI, so every process path is exercised without model calls."""

import json
import os
import sys
import time
from uuid import uuid4

import pytest

from boss.errors import Outcome
from boss.runner import WorkspaceError, run_slice
from boss.worker import SCHEMA_TOOL, WORKER_TOOLS, IsolationError, SliceSpec

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

    def run(mode, *, timeout_s=10.0, init=INIT, **extra_env):
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "FAKE_MODE": mode,
            "FAKE_INIT": json.dumps(init),
            "FAKE_RESULT": json.dumps(RESULT),
            "FAKE_CHILD_PID": str(child_pid),
            **extra_env,
        }
        spec = SliceSpec(session_id=uuid4(), resume=False, prompt="Do it.", model="haiku",
                         cap_micros=100_000)  # fmt: skip
        return run_slice(spec, ws, tmp_path / "logs" / "w1.jsonl", env=env, timeout_s=timeout_s,
                         grace_s=0.5, executable=str(cli))  # fmt: skip

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


def test_timeout_stops_the_worker_and_its_children(fake):
    start = time.monotonic()
    run = fake("hang", timeout_s=1.5)
    assert run.outcome is Outcome.TIMEOUT
    assert time.monotonic() - start < 10
    assert_dead(fake.child_pid)


def test_worker_ignoring_sigint_and_sigterm_is_still_killed(fake):
    run = fake("stubborn", timeout_s=1.5)
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
    run = fake("graceful", timeout_s=1.0)
    assert run.outcome is Outcome.TIMEOUT
    assert run.usage.cost_micros == 5400
