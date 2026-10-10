"""`antstreet doctor --live` asks one real worker to write outside its folder. These tests play the
CLI: one that refuses the write, one that lets it through, and one whose worker never tries."""

import sys
from pathlib import Path

import pytest

from antstreet.doctor import run_doctor

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
    "total_cost_usd": 0.004,
    "modelUsage": {"m": {"inputTokens": 10, "outputTokens": 5}},
    "structured_output": {"status": "blocked", "reason": "the write was refused"},
}
DENIED = {"type": "system", "subtype": "permission_denied", "tool_name": "Write"}
FAKE = f"""#!{sys.executable}
import json, os, re, sys, time
argv = sys.argv[1:]
if argv[:1] == ["--version"]:
    print("2.1.285 (Claude Code)")
elif argv[:2] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True}}))
elif "stream-json" not in argv:            # the doctor's live login call
    print(json.dumps({RESULT!r} | {{"result": "ok"}}))
else:                                       # the canary slice
    mode = open(os.path.join(os.environ["HOME"], "canary_mode")).read().strip()
    init = {INIT!r}
    if mode == "unisolated":
        init = init | {{"mcp_servers": [{{"name": "x"}}]}}
    print(json.dumps(init), flush=True)
    target = re.search(r"create the file (\\S+)", argv[-1]).group(1)
    if mode == "refused":
        print(json.dumps({DENIED!r}), flush=True)
    elif mode == "escaped":
        open(target, "w").write("canary")
    print(json.dumps({RESULT!r}), flush=True)
    if mode == "unisolated":
        # A worker that is not isolated is still running when the runner refuses it. If this fake
        # exited first, the runner's killpg would hit a zombie group leader, which macOS answers
        # with EPERM (src/antstreet/runner.py `_stop` catches only ProcessLookupError).
        time.sleep(30)
"""


@pytest.fixture
def doctor(tmp_path, monkeypatch):
    monkeypatch.delenv("BOSS_GATE_SANDBOX", raising=False)
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE)
    cli.chmod(0o755)
    cwd = tmp_path / "work"
    cwd.mkdir()

    def run(mode, live=True):
        (tmp_path / "canary_mode").write_text(mode)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
        return {c.name: c for c in run_doctor(env, cwd, live=live, executable=str(cli))}

    return run


def test_a_refused_write_passes_the_canary(doctor):
    check = doctor("refused")["worker path rules"]
    assert check.ok and check.advice == ""
    assert check.detail == "a write outside the worker's folder was refused (one live call)"


def test_a_write_that_lands_outside_the_folder_fails_the_doctor(doctor):
    check = doctor("escaped")["worker path rules"]
    assert not check.ok and "OUTSIDE its folder" in check.detail
    assert "do not run antstreet with this CLI version" in check.fix


def test_a_worker_that_never_tries_is_inconclusive_not_a_pass(doctor):
    check = doctor("idle")["worker path rules"]
    assert check.ok and check.detail.startswith("inconclusive: the worker did not attempt")
    assert "re-run with --live" in check.advice


def test_a_worker_that_does_not_start_isolated_fails_the_canary(doctor):
    check = doctor("unisolated")["worker path rules"]
    assert not check.ok and "did not start isolated" in check.detail


def test_the_canary_runs_only_when_asked_for_a_live_check(doctor):
    assert "worker path rules" not in doctor("refused", live=False)
    assert "worker path rules" in doctor("refused", live=True)


def test_the_canary_leaves_nothing_behind(doctor, tmp_path):
    doctor("refused", live=False)  # writes the fake's mode file
    before = sorted(p.name for p in Path(tmp_path).iterdir())
    doctor("escaped")
    assert sorted(p.name for p in Path(tmp_path).iterdir()) == before
