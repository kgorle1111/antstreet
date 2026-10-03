"""The worker's thinking budget: validated, recorded with the run's configuration, and set on the
child's environment (and only there), so the default of leaving the CLI's own stays untouched."""

import sys
from uuid import uuid4

import pytest
from test_firm import C01, C02, C03, GOOD, Script, run, sheet, step

from boss.firm import FirmConfig, config_data, config_from_data, started_config
from boss.ledger import read_events
from boss.rundir import RunPaths
from boss.runner import run_slice
from boss.worker import SCHEMA_TOOL, WORKER_TOOLS, SliceSpec, worker_env

# Reports the MAX_THINKING_TOKENS it was started with, as the reason in its status.
FAKE_CLI = f"""#!{sys.executable}
import json, os
say = lambda e: print(json.dumps(e), flush=True)
say({{"type": "system", "subtype": "init", "tools": {[*WORKER_TOOLS, SCHEMA_TOOL]!r},
     "mcp_servers": [], "permissionMode": "dontAsk", "claude_code_version": "2.1.285"}})
say({{"type": "result", "subtype": "success", "total_cost_usd": 0.001, "modelUsage": {{}},
     "structured_output": {{"status": "done",
                           "reason": os.environ.get("MAX_THINKING_TOKENS", "unset")}}}})
"""


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02), ("test_c03.py", C03)):
        (p.checks / name).write_text(code)
    return p


def slice_with(tmp_path, thinking, env):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    (tmp_path / "ws").mkdir(exist_ok=True)
    spec = SliceSpec(uuid4(), False, "Do it.", "haiku", 100_000, thinking_tokens=thinking)
    return run_slice(
        spec, tmp_path / "ws", tmp_path / "log.jsonl", env=env, grace_s=0.5, executable=str(cli)
    )


@pytest.mark.parametrize("thinking, seen", [(None, "unset"), (0, "0"), (4096, "4096")])
def test_the_slice_budget_reaches_the_workers_environment(tmp_path, thinking, seen):
    run_ = slice_with(tmp_path, thinking, {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)})
    assert run_.status == {"status": "done", "reason": seen}


def test_an_inherited_budget_is_not_the_default_a_worker_sees(tmp_path):
    # cli.py builds the env with worker_env, which drops it; the unset default must stay unset.
    env = worker_env({"HOME": str(tmp_path), "PATH": "/usr/bin", "MAX_THINKING_TOKENS": "0"})
    env["PATH"] = "/usr/bin:/bin"
    assert slice_with(tmp_path, None, env).status["reason"] == "unset"


@pytest.mark.parametrize("bad", [-1, 1.5, "0", True])
def test_a_bad_budget_is_refused_by_the_slice_and_the_config(bad):
    with pytest.raises(ValueError, match="thinking tokens"):
        SliceSpec(uuid4(), False, "Do it.", "haiku", 1_000, thinking_tokens=bad)
    with pytest.raises(ValueError, match="thinking tokens"):
        FirmConfig(thinking_tokens=bad)


def test_the_default_config_leaves_thinking_unset_and_old_ledgers_still_load():
    assert FirmConfig().thinking_tokens is None
    recorded = config_data(FirmConfig())
    del recorded["thinking_tokens"]  # a `started` event written before the field existed
    assert config_from_data(recorded) == FirmConfig()


def test_the_configured_budget_is_recorded_on_started_and_reaches_every_slice(paths):
    worker = Script(step(GOOD, "done"))
    run(paths, worker, sheet(), config=FirmConfig(thinking_tokens=2000))
    assert [s.thinking_tokens for s in worker.specs] == [2000]
    # `boss resume` takes the configuration back from the `started` event.
    assert started_config(read_events(paths.ledger)) == FirmConfig(thinking_tokens=2000)
