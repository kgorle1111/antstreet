"""A hook event after `system/init` is an isolation failure too, not just a counted curiosity."""

import json
import os
import sys
import time
from uuid import uuid4

import pytest

from boss.errors import Outcome
from boss.runner import run_slice
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
    "modelUsage": {"m": {"inputTokens": 5, "outputTokens": 7}},
    "session_id": "s-1",
}
ASSISTANT = {"type": "assistant", "note": "working"}
HOOK = {"type": "system", "subtype": "hook_started", "hook_name": "late"}

# Spawns a child, prints the scripted events, then keeps running (or exits).
FAKE_CLI = f"""#!{sys.executable}
import json, os, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
open(os.environ["FAKE_CHILD_PID"], "w").write(str(child.pid))
for event in json.loads(os.environ["FAKE_SCRIPT"]):
    print(json.dumps(event), flush=True)
if os.environ["FAKE_END"] == "sleep":
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

    def run(script, *, end="sleep"):
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "FAKE_SCRIPT": json.dumps(script),
            "FAKE_END": end,
            "FAKE_CHILD_PID": str(child_pid),
        }
        spec = SliceSpec(
            session_id=uuid4(), resume=False, prompt="Do it.", model="haiku", cap_micros=100_000
        )
        return run_slice(
            spec,
            ws,
            tmp_path / "logs" / "w1.jsonl",
            env=env,
            timeout_s=30.0,
            grace_s=0.5,
            executable=str(cli),
        )

    run.child_pid = child_pid
    run.log = tmp_path / "logs" / "w1.jsonl"
    return run


def assert_dead(pid_file):
    pid = int(pid_file.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize("subtype", ["hook_started", "hook_response", "hook_progress"])
def test_a_hook_event_after_init_stops_the_process_and_is_refused(fake, subtype):
    hook = HOOK | {"subtype": subtype}
    start = time.monotonic()
    with pytest.raises(IsolationError, match="1 hook event"):
        fake([INIT, ASSISTANT, hook])
    assert time.monotonic() - start < 10
    assert_dead(fake.child_pid)


def test_the_output_up_to_and_including_the_hook_event_is_recorded(fake):
    with pytest.raises(IsolationError):
        fake([INIT, ASSISTANT, HOOK])
    recorded = [json.loads(line) for line in fake.log.read_text().splitlines()]
    assert recorded == [INIT, ASSISTANT, HOOK]


def test_a_hook_event_after_a_finished_result_still_fails_the_slice(fake):
    with pytest.raises(IsolationError, match="hook event"):
        fake([INIT, RESULT, HOOK], end="sleep")
    assert_dead(fake.child_pid)


def test_a_hook_event_in_the_last_line_before_exit_is_refused(fake):
    with pytest.raises(IsolationError, match="hook event"):
        fake([INIT, RESULT, HOOK], end="exit")


def test_events_that_only_look_like_hooks_do_not_fail_the_slice(fake):
    script = [INIT, {"type": "system", "subtype": "status"}, {"type": "hook_started"}, RESULT]
    run = fake(script, end="exit")
    assert run.outcome is Outcome.COMPLETED
