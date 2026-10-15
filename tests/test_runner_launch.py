"""T73: the worker CLI starts only once its process group is recorded in `logs/<worker>.pgid`.

`resume` finds a worker left running by a killed `antstreet` only through that file. If the CLI
could start before the file exists, an `antstreet` killed in between leaves a worker making paid
calls that `resume` cannot see: it books the slice and runs it again beside it.
"""

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from uuid import uuid4

import pytest

from antstreet import runner
from antstreet.errors import Outcome
from antstreet.runner import _GO_SHIM, _go_message, pgid_file, run_slice
from antstreet.worker import SCHEMA_TOOL, WORKER_TOOLS, SliceSpec

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


@pytest.fixture
def fake(tmp_path):
    cli = tmp_path / "fake-claude"
    # The first thing the fake does is leave a marker: a real CLI would be calling the model then.
    cli.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent(
            """
            import fcntl, json, os, sys
            def is_open(fd):
                try:
                    fcntl.fcntl(fd, fcntl.F_GETFD)
                    return True
                except OSError:
                    return False
            seen = json.dumps({
                "env": dict(os.environ),
                "argv": sys.argv,
                "cwd": os.getcwd(),
                "pid": os.getpid(),
                "pgid": os.getpgrp(),
                "stdin_is_null": os.path.samestat(os.fstat(0), os.stat(os.devnull)),
                "extra_fds": [fd for fd in range(3, 256) if is_open(fd)],
            })
            # Next to the fake, not from its env: a CLI started with no env must still show.
            here = os.path.dirname(os.path.realpath(__file__))
            open(os.path.join(here, "cli-ran"), "w").write(seen)
            print(os.environ["FAKE_INIT"], flush=True)
            print(os.environ["FAKE_RESULT"], flush=True)
            """
        )
    )
    cli.chmod(0o755)
    ws = tmp_path / "ws"
    ws.mkdir()
    marker = tmp_path / "cli-ran"  # where the fake writes it
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_INIT": json.dumps(INIT),
        "FAKE_RESULT": json.dumps(RESULT),
        # The fake is Python too: without this its own start would set LC_CTYPE and hide a leak.
        "PYTHONCOERCECLOCALE": "0",
    }
    spec = SliceSpec(
        session_id=uuid4(), resume=False, prompt="Do it.", model="haiku", cap_micros=100_000
    )
    return {
        "cli": cli,
        "ws": ws,
        "marker": marker,
        "env": env,
        "spec": spec,
        "log": tmp_path / "logs" / "w1.jsonl",
    }


def _gone(pid: int, within_s: float = 5.0) -> bool:
    """True once no live process has this pid (a zombie counts as gone: it runs nothing)."""
    deadline = time.monotonic() + within_s
    while time.monotonic() < deadline:
        stat = subprocess.run(
            ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
        if not stat or stat.startswith("Z"):
            return True
        time.sleep(0.05)
    return False


def test_a_failed_record_stops_the_launch_before_the_cli_runs_and_raises(fake, monkeypatch):
    seen: dict[str, int] = {}

    def failing_record(path, pgid):
        seen["pgid"] = pgid
        deadline = time.monotonic() + 2.0  # give a CLI that started too early time to show it
        while time.monotonic() < deadline and not fake["marker"].exists():
            time.sleep(0.02)
        raise OSError("disk full")

    monkeypatch.setattr(runner, "_record_pgid", failing_record)
    with pytest.raises(OSError, match="disk full"):
        run_slice(
            fake["spec"], fake["ws"], fake["log"], env=fake["env"], grace_s=0.5,
            executable=str(fake["cli"]),
        )  # fmt: skip
    assert not fake["marker"].exists(), "the worker CLI ran before its group was recorded"
    assert _gone(seen["pgid"])
    assert not pgid_file(fake["log"]).exists()


PARENT = """
import json, os, signal, sys
from pathlib import Path
from uuid import UUID
from antstreet import runner
from antstreet.worker import SliceSpec

args = json.loads(sys.argv[1])

def die_while_recording(path, pgid):  # antstreet SIGKILLed between the launch and the record
    Path(args["child"]).write_text(str(pgid))
    os.kill(os.getpid(), signal.SIGKILL)

runner._record_pgid = die_while_recording
spec = SliceSpec(session_id=UUID(args["session"]), resume=False, prompt="Do it.",
                 model="haiku", cap_micros=100_000)
runner.run_slice(spec, Path(args["ws"]), Path(args["log"]), env=args["env"],
                 executable=args["cli"])
"""


def test_antstreet_killed_before_the_record_leaves_no_cli_running_and_nothing_spent(fake, tmp_path):
    child = tmp_path / "child.pid"
    args = {
        "child": str(child),
        "session": str(fake["spec"].session_id),
        "ws": str(fake["ws"]),
        "log": str(fake["log"]),
        "env": fake["env"],
        "cli": str(fake["cli"]),
    }
    parent = subprocess.run(
        [sys.executable, "-c", PARENT, json.dumps(args)], capture_output=True, timeout=30
    )
    assert parent.returncode == -signal.SIGKILL, parent.stderr
    pid = int(child.read_text())
    time.sleep(1.0)  # a CLI started too early writes its marker well within this
    assert not fake["marker"].exists(), "a worker ran that no pgid file records"
    assert _gone(pid), "the launched child is still running after antstreet died"
    assert not pgid_file(fake["log"]).exists()


def test_the_cli_runs_with_the_same_env_argv_stdin_and_group_as_before(fake):
    run = run_slice(
        fake["spec"], fake["ws"], fake["log"], env=fake["env"], grace_s=0.5,
        executable=str(fake["cli"]),
    )  # fmt: skip
    assert run.outcome is Outcome.COMPLETED
    assert run.usage.cost_micros == 5400
    seen = json.loads(fake["marker"].read_text())
    fake["marker"].unlink()
    subprocess.run([fake["cli"]], env=fake["env"], capture_output=True, check=True)  # as before
    direct = json.loads(fake["marker"].read_text())
    assert "LC_CTYPE" not in direct["env"]  # so a shim that sets it would show
    assert seen["env"] == direct["env"]
    assert seen["argv"][0] == str(fake["cli"])
    assert str(fake["spec"].session_id) in seen["argv"]  # resume's identity check reads this
    assert seen["cwd"] == os.path.realpath(fake["ws"])
    assert seen["pgid"] == seen["pid"]  # its own session: the recorded pgid is its pid
    assert seen["stdin_is_null"]
    assert seen["extra_fds"] == []  # the go pipe is not handed to the worker
    assert not pgid_file(fake["log"]).exists()


def test_a_bare_executable_is_found_on_the_worker_path_and_a_missing_one_raises(fake):
    bindir = fake["cli"].parent / "bin"
    bindir.mkdir()
    (bindir / "fake-claude").symlink_to(fake["cli"])
    env = fake["env"] | {"PATH": f"{bindir}:/usr/bin:/bin"}
    run = run_slice(
        fake["spec"], fake["ws"], fake["log"], env=env, grace_s=0.5, executable="fake-claude"
    )
    assert run.outcome is Outcome.COMPLETED
    assert json.loads(fake["marker"].read_text())["argv"][0].endswith("fake-claude")
    with pytest.raises(FileNotFoundError):
        run_slice(
            fake["spec"], fake["ws"], fake["log"], env=env, grace_s=0.5,
            executable="no-such-claude",
        )  # fmt: skip


@pytest.mark.parametrize("cut", [0, 1, 5, -1])
def test_a_go_message_cut_short_by_a_crash_never_runs_the_cli(fake, cut):
    message = _go_message(fake["env"])
    read, write = os.pipe()
    shim = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", _GO_SHIM, str(read), str(fake["cli"]), "claude"],
        pass_fds=(read,),
    )
    os.close(read)
    os.write(write, message[: cut % len(message)])  # -1: all but the last byte
    os.close(write)  # what the kernel does when antstreet dies mid-write
    assert shim.wait(timeout=10) == 75
    assert not fake["marker"].exists()


def test_a_launched_child_that_dies_before_the_go_is_a_crash_not_an_exception(fake, monkeypatch):
    record = runner._record_pgid

    def record_then_lose_the_child(path, pgid):
        record(path, pgid)
        os.killpg(pgid, signal.SIGKILL)
        assert _gone(pgid)

    monkeypatch.setattr(runner, "_record_pgid", record_then_lose_the_child)
    run = run_slice(
        fake["spec"], fake["ws"], fake["log"], env=fake["env"], grace_s=0.5,
        executable=str(fake["cli"]),
    )  # fmt: skip
    assert run.outcome is Outcome.CRASHED
    assert run.usage.cost_micros is None
    assert not fake["marker"].exists()
    assert not pgid_file(fake["log"]).exists()
