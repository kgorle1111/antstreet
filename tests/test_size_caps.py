"""Size caps: a worker must not be able to fill the disk through its folder or its log."""

import json
import os
import sys
from uuid import uuid4

import pytest

from boss.approval import content_hashes
from boss.errors import Outcome
from boss.firm import FirmConfig, run_firm
from boss.ledger import Event, EventType, LedgerWriter, read_events, total
from boss.limits import RunLimits
from boss.rundir import RunPaths, WorkspaceTooBig, workspace_bytes
from boss.runner import LOG_CUT, SliceRun, run_slice
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, Task, TermSheet
from boss.worker import SliceSpec

CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
SHEET = TermSheet(
    "Reverse a string.",
    500_000,
    (Round(1, 500_000, 1),),
    (CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
    (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
    True,
)


def test_workspace_bytes_counts_files_and_never_follows_a_link(tmp_path):
    ws, outside = tmp_path / "ws", tmp_path / "outside"
    (ws / "sub").mkdir(parents=True)
    outside.mkdir()
    (ws / "a.py").write_bytes(b"x" * 100)
    (ws / "sub" / "b.py").write_bytes(b"y" * 250)
    (outside / "huge.bin").write_bytes(b"z" * 100_000)
    os.symlink(outside / "huge.bin", ws / "link.bin")
    os.symlink(outside, ws / "linked_dir")
    assert 350 <= workspace_bytes(ws, 10**9) < 1_000  # the links themselves, not their targets
    assert workspace_bytes(tmp_path / "missing", 10**9) == 0


def test_counting_stops_once_the_limit_is_passed(tmp_path):
    for n in range(50):
        (tmp_path / f"f{n}").write_bytes(b"x" * 1_000)
    counted = workspace_bytes(tmp_path, 3_000)
    assert 3_000 < counted <= 4_000  # it did not read all 50,000 bytes' worth of files


def fund(tmp_path, size, limit):
    paths = RunPaths(tmp_path / "run")
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(CHECK)
    calls = []

    def worker(spec, workspace, log_path, *, env):
        calls.append(spec)
        (workspace / "rev.py").write_text("def reverse(s):\n    return s[::-1]\n")
        (workspace / "blob.bin").write_bytes(b"x" * size)
        return SliceRun(Outcome.COMPLETED, Usage(9_000, 1, 1, 0), None, "s", 0, 0.1, log_path)

    with LedgerWriter(paths.ledger) as ledger:
        data = {"hashes": content_hashes(SHEET, paths.checks)}
        ledger.append(
            Event(run="r", round=0, actor="investor", event=EventType.APPROVED, data=data)
        )
        config = FirmConfig(limits=RunLimits(max_workspace_bytes=limit))
        report = run_firm(
            SHEET, paths, ledger, "r", env={"HOME": "/h"}, config=config,
            ask=lambda q: "n", say=lambda line: None, slice_runner=worker,
        )  # fmt: skip
    return report, read_events(paths.ledger), calls


def test_a_folder_over_the_limit_stops_the_run_before_the_gate_copies_it(tmp_path):
    report, events, calls = fund(tmp_path, size=5 * 2**20, limit=2 * 2**20)
    assert report.stopped.startswith("stopped: the folder of w1 holds more than 2 MB")
    assert [e for e in events if e.event is EventType.CHECK_RESULT] == []
    [stop] = [e for e in events if e.event is EventType.STOPPED]
    assert stop.actor == "rule" and "the gate copies it for every check" in stop.data["reason"]
    assert total(events).cost_micros == 9_000 and len(calls) == 1  # the slice is on the books


def test_a_folder_inside_the_limit_is_gated_as_usual(tmp_path):
    report, events, _ = fund(tmp_path, size=1_000, limit=2 * 2**20)
    assert report.all_passed and report.stopped is None


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_the_folder_limit_must_be_a_positive_whole_number(bad):
    with pytest.raises(ValueError, match="max_workspace_bytes"):
        RunLimits(max_workspace_bytes=bad)
    assert str(WorkspaceTooBig("w1", 5 * 2**20, 2 * 2**20)).startswith("the folder of w1")


INIT = {
    "type": "system",
    "subtype": "init",
    "tools": ["Read", "Write", "Edit", "StructuredOutput"],
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
    "modelUsage": {"m": {"inputTokens": 10, "outputTokens": 5}},
}
NOISY = f"""#!{sys.executable}
import json
print(json.dumps({INIT!r}), flush=True)
for n in range(2000):
    print(json.dumps({{"type": "assistant", "n": n, "pad": "x" * 200}}), flush=True)
print(json.dumps({RESULT!r}), flush=True)
"""


def noisy(tmp_path, max_log_bytes):
    cli = tmp_path / "fake-claude"
    cli.write_text(NOISY)
    cli.chmod(0o755)
    ws = tmp_path / "ws"
    ws.mkdir()
    spec = SliceSpec(uuid4(), False, "Do it.", "haiku", 100_000)
    log = tmp_path / "logs" / "w1.jsonl"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    run = run_slice(spec, ws, log, env=env, executable=str(cli), max_log_bytes=max_log_bytes)
    return run, log


def test_a_log_stops_growing_at_its_cap_and_the_slices_result_is_still_read(tmp_path):
    run, log = noisy(tmp_path, max_log_bytes=20_000)
    assert run.outcome is Outcome.COMPLETED and run.usage.cost_micros == 5_400
    text = log.read_text()
    # The line that would cross the cap is replaced by the marker, so the log ends just under it.
    assert 19_700 <= len(text) <= 20_000 + len(LOG_CUT) and text.endswith(LOG_CUT)
    assert text.count(LOG_CUT) == 1
    assert all(json.loads(line) for line in text.splitlines())  # still one JSON value per line


def test_a_log_under_its_cap_is_complete(tmp_path):
    run, log = noisy(tmp_path, max_log_bytes=10**9)
    lines = log.read_text().splitlines()
    assert len(lines) == 2002 and LOG_CUT.strip() not in lines
