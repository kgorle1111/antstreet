"""A session to resume that the CLI no longer has (B11): the next attempt starts a new session and
the lost one is never the worker's fault.

The fake `claude` keeps a session store in a folder, like the real CLI: `--session-id X` creates
X, `--resume X` needs it to exist and otherwise says what the real CLI said in the probe (CLI
2.1.285): "No conversation found", on stderr, with no stream and exit code 1. Wiping the folder
between two slices reproduces "the CLI's session store was cleared between runs". No model is
called.
"""

import functools
import sys
from uuid import uuid4

import pytest

from boss.approval import content_hashes
from boss.errors import Outcome
from boss.firm import FirmConfig, run_firm
from boss.gate import run_gate
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.rule import FiringPolicy
from boss.rundir import RunPaths
from boss.runner import run_slice
from boss.termsheet import CheckSpec, Round, Task, TermSheet
from boss.worker import SliceSpec

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
GOOD = "def reverse(s):\\n    return s[::-1]\\n"
HALF = "def reverse(s):\\n    return s\\n"

FAKE_CLI = f"""#!{sys.executable}
import json, os, shutil, sys
argv = sys.argv[1:]
store = os.environ["FAKE_STORE"]
os.makedirs(store, exist_ok=True)
resume = "--resume" in argv
sid = argv[argv.index("--resume" if resume else "--session-id") + 1]
path = os.path.join(store, sid)
if resume and not os.path.exists(path):
    print("No conversation found with session ID: " + sid, file=sys.stderr, flush=True)
    sys.exit(1)
if not resume and os.path.exists(path):
    print("Error: Session ID " + sid + " is already in use.", file=sys.stderr, flush=True)
    sys.exit(1)
calls = os.path.join(store, "calls")
n = int(open(calls).read()) + 1 if os.path.exists(calls) else 1
open(calls, "w").write(str(n))
turns = int(open(path).read()) + 1 if resume else 1
open(path, "w").write(str(turns))
say = lambda e: print(json.dumps(e), flush=True)
say({{"type": "system", "subtype": "init", "tools": ["Read", "Write", "Edit", "StructuredOutput"],
     "mcp_servers": [], "permissionMode": "dontAsk", "claude_code_version": "2.1.285",
     "session_id": sid}})
done = n >= int(os.environ["FAKE_GOOD_FROM"])
open("rev.py", "w").write("{GOOD}" if done else "{HALF}")
say({{"type": "result", "subtype": "success", "is_error": False, "terminal_reason": "completed",
     "session_id": sid, "total_cost_usd": 0.01 * turns,
     "modelUsage": {{"m": {{"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}}}},
     "structured_output": {{"status": "done" if done else "continuing", "reason": "rev.py"}}}})
if str(n) in os.environ.get("FAKE_WIPE_AFTER", "").split(","):
    for name in os.listdir(store):
        if name != "calls":
            os.remove(os.path.join(store, name))
"""


@pytest.fixture
def cli(tmp_path):
    path = tmp_path / "fake-claude"
    path.write_text(FAKE_CLI)
    path.chmod(0o755)
    return path


def env_for(tmp_path, **extra):
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_STORE": str(tmp_path / "store"),
    } | {k: str(v) for k, v in extra.items()}


def spec(session, *, resume):
    return SliceSpec(
        session_id=session, resume=resume, prompt="Do it.", model="haiku", cap_micros=100_000
    )


def test_the_runner_names_a_resume_of_a_session_the_cli_does_not_have(cli, tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    env = env_for(tmp_path, FAKE_GOOD_FROM=1)
    session = uuid4()
    log = tmp_path / "logs" / "w1.jsonl"
    lost = run_slice(spec(session, resume=True), workspace, log, env=env, executable=str(cli))
    assert lost.outcome is Outcome.SESSION_LOST
    assert lost.exit_code == 1 and lost.usage.cost_micros is None and lost.status is None
    assert "No conversation found" in lost.stderr_tail
    # Starting the session first, the same resume works: the fake is not simply failing.
    first = run_slice(spec(session, resume=False), workspace, log, env=env, executable=str(cli))
    again = run_slice(spec(session, resume=True), workspace, log, env=env, executable=str(cli))
    assert (first.outcome, again.outcome) == (Outcome.COMPLETED, Outcome.COMPLETED)
    assert again.usage.cost_micros == 20_000  # the session's cumulative total


def sheet() -> TermSheet:
    tasks = (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),)
    checks = (CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),)
    return TermSheet("Reverse a string.", 500_000, (Round(1, 500_000, 1),), checks, tasks, True)


def run_with_fake(tmp_path, cli, *, wipe_after, good_from, policy=None):
    paths = RunPaths(tmp_path / "run")
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(C01)
    s, sleeps = sheet(), []
    env = env_for(tmp_path, FAKE_WIPE_AFTER=wipe_after, FAKE_GOOD_FROM=good_from)
    config = FirmConfig(policy=policy or FiringPolicy())
    with LedgerWriter(paths.ledger) as ledger:
        data = {"hashes": content_hashes(s, paths.checks)}
        ledger.append(
            Event(run="r1", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
        report = run_firm(
            s, paths, ledger, "r1", env=env, config=config, ask=lambda q: "n", say=lambda _: None,
            slice_runner=functools.partial(run_slice, executable=str(cli)), gate=run_gate,
            sleep=sleeps.append,
        )  # fmt: skip
    return report, read_events(paths.ledger), sleeps


def of(events, kind):
    return [e for e in events if e.event is kind]


def test_a_worker_whose_session_was_cleared_starts_a_new_one_and_is_not_fired(tmp_path, cli):
    # Slice 1 works and proves its session; the store is then cleared, so slice 2 cannot resume.
    # Counted against the worker, the lost slice would make slice 3 its third without progress
    # and get it fired (stall_slices=3) before slice 4 passes.
    report, events, sleeps = run_with_fake(
        tmp_path, cli, wipe_after="1", good_from=3, policy=FiringPolicy(stall_slices=3)
    )
    assert report.all_passed
    assert of(events, EventType.FIRED) == [] and of(events, EventType.ABANDONED) == []
    ends = of(events, EventType.SLICE_END)
    outcomes = [e.data["outcome"] for e in ends]
    assert outcomes == ["completed", "session_lost", "completed", "completed"]
    starts = of(events, EventType.SLICE_START)
    a, b = starts[0].data["session"], starts[2].data["session"]
    assert [e.data["session"] for e in starts] == [a, a, b, b] and a != b  # on slice_start
    assert [e.data["slice"] for e in starts] == [1, 2, 3, 4]
    assert sleeps == [0.0]  # no backoff for it
    # The lost slice cost nothing (the CLI never reached the model) and is not charged at its cap;
    # the new session's totals start again from zero.
    assert [e.cost_micros for e in ends] == [10_000, None, 10_000, 10_000]
    assert "No conversation found" not in (tmp_path / "run" / "ledger.jsonl").read_text()
