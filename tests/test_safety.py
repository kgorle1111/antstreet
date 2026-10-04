"""Controls (and pinned limits) that no other test file proves; docs/THREAT_MODEL.md cites these.

Tests named `test_accepted_risk_*` do not prove a control. They pin a known limit of the gate or
the ledger, so that a change which removes the limit fails here and the threat model gets updated.
"""

import contextlib
import dataclasses
import json
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from boss_init import BOSS_INIT
from gate_forgers import NONCE_READER

from boss import termsheet
from boss.approval import NotApprovedError, content_hashes, require_approval
from boss.boss import draft_term_sheet
from boss.budget import remaining
from boss.errors import Outcome
from boss.firm import FirmConfig, run_firm
from boss.gate import Check, CheckStatus, run_gate
from boss.ledger import (
    Event,
    EventType,
    LedgerCorruptError,
    LedgerWriter,
    read_events,
    total,
)
from boss.rundir import RunPaths, assemble_product
from boss.runner import SliceRun
from boss.sandbox import SandboxMode
from boss.state import RunState, TaskState
from boss.stream import Usage
from boss.termsheet import CheckSpec, Round, Task, TermSheet, validate

CHECK = "from rev import reverse\n\ndef test_reverse():\n    assert reverse('ab') == 'ba'\n"
RIGHT = "def reverse(s):\n    return s[::-1]\n"
WRONG = "def reverse(s):\n    return s\n"
# Rewrites the gate's own JUnit report as a clean pass and exits 0, using the path in argv.
FORGER = (
    "import os, sys\n"
    "def forge():\n"
    "    path = next(a for a in sys.argv if a.startswith('--junitxml=')).split('=', 1)[1]\n"
    "    with open(path, 'w') as fh:\n"
    '        fh.write(\'<testsuite tests="1" failures="0" errors="0" skipped="0"/>\')\n'
    "    os._exit(0)\n"
)


def gate_one(
    tmp_path: Path,
    files: dict[str, str],
    check: str = CHECK,
    timeout_s: float = 30.0,
    sandbox: SandboxMode | None = None,
):
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    ws.mkdir()
    checks.mkdir()
    (checks / "test_c01.py").write_text(check)
    for name, code in files.items():
        (ws / name).write_text(code)
    [result] = run_gate(
        ws, checks, [Check("c01", "test_c01.py")], timeout_s=timeout_s, sandbox=sandbox
    )
    return result


# --- the gate: forged verdicts ---------------------------------------------------------------


def test_forged_startup_files_in_the_workspace_never_run(tmp_path):
    ran = tmp_path / "ran"
    marker = f"open({str(ran)!r}, 'a').write('x')\n"
    files = {"rev.py": WRONG}
    for name in ("pytest.py", "sitecustomize.py", "usercustomize.py", "conftest.py"):
        files[name] = marker + FORGER + "forge()\n"
    result = gate_one(tmp_path, files)
    # A real, failing pytest run: had any forger executed, the report would say "1 passed".
    assert result.status is CheckStatus.FAILED
    assert result.detail == "pytest exited 1"
    assert not ran.exists()


def test_exit_zero_after_a_failing_report_is_not_a_pass(tmp_path):
    exits_zero = "import atexit, os\natexit.register(lambda: os._exit(0))\n"
    result = gate_one(tmp_path, {"rev.py": exits_zero + WRONG})
    assert result.exit_code == 0
    assert result.status is CheckStatus.FAILED
    assert result.detail == "report shows 1 failed, 0 errors, 0 skipped"


def test_code_that_rewrites_the_report_and_exits_zero_is_not_a_pass(tmp_path):
    aimed = "import atexit\n" + FORGER + "atexit.register(forge)\n" + WRONG
    result = gate_one(tmp_path, {"rev.py": aimed})
    assert result.status is CheckStatus.FAILED
    assert "no valid proof" in result.detail


def test_accepted_risk_code_aimed_at_the_gate_can_forge_a_pass(tmp_path):
    # Code that reads the per-run nonce out of the gate's plugin in its own process signs the
    # proof itself (T12). If this fails the attack is closed: update THREAT_MODEL T12 and the kn:
    # comment in gate.py.
    result = gate_one(tmp_path, {"rev.py": NONCE_READER + WRONG})
    assert result.status is CheckStatus.PASSED
    assert result.detail == "1 passed"


def test_accepted_risk_worker_code_run_by_the_gate_has_host_access(tmp_path):
    outside = tmp_path / "written-outside-the-gate-copy"
    code = f"open({str(outside)!r}, 'w').write('x')\n" + WRONG
    result = gate_one(tmp_path, {"rev.py": code}, sandbox=SandboxMode.OFF)
    assert result.status is CheckStatus.FAILED
    assert outside.read_text() == "x"


def test_accepted_risk_a_detached_child_outlives_the_gate_timeout(tmp_path):
    pid_file = tmp_path / "detached.pid"
    detached = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
        "                     start_new_session=True)\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n"
    )
    result = gate_one(tmp_path, {"rev.py": detached}, timeout_s=2.0, sandbox=SandboxMode.OFF)
    pid = int(pid_file.read_text())
    try:
        assert result.status is CheckStatus.TIMEOUT
        os.kill(pid, 0)  # still alive: killing the process group cannot reach a new session
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


# --- term sheet validation runs code and binds approval --------------------------------------


def sheet_of(check_file: str = "test_c01.py") -> TermSheet:
    return TermSheet(
        idea="Reverse a string.",
        budget_micros=500_000,
        rounds=(Round(1, 500_000, 1),),
        checks=(CheckSpec("c01", "reverses a word", check_file, "t1"),),
        tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
    )


def write_checks(root: Path) -> Path:
    checks = root / "checks"
    checks.mkdir(exist_ok=True)
    (checks / "test_c01.py").write_text(CHECK)
    return checks


def approval_event(sheet: TermSheet, checks: Path, actor: str = "investor") -> Event:
    hashes = content_hashes(sheet, checks)
    return Event(run="r1", round=0, actor=actor, event=EventType.APPROVED, data={"hashes": hashes})


def test_accepted_risk_check_code_runs_during_validation_before_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "off")
    ran = tmp_path / "ran-before-approval"
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text(
        f"open({str(ran)!r}, 'w').write('x')\ndef test_x():\n    assert False\n"
    )
    validate(sheet_of(), checks)  # sound sheet, check fails on an empty workspace: no problems
    assert ran.read_text() == "x"


def test_a_check_that_hangs_on_an_empty_workspace_is_rejected(tmp_path, monkeypatch):
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "test_c01.py").write_text("import time\ntime.sleep(60)\ndef test_x():\n    pass\n")
    real = termsheet.run_gate
    monkeypatch.setattr(
        termsheet, "run_gate", lambda ws, cd, checks, timeout_s: real(ws, cd, checks, timeout_s=2)
    )
    assert termsheet.empty_workspace_problems(sheet_of(), checks) == [
        "check c01 times out on an empty workspace"
    ]


CHANGES = {
    "budget": lambda s: dataclasses.replace(s, budget_micros=900_000),
    "idea": lambda s: dataclasses.replace(s, idea="Something else entirely."),
    "round-threshold": lambda s: dataclasses.replace(s, rounds=(Round(1, 500_000, 2),)),
    "task-brief": lambda s: dataclasses.replace(
        s, tasks=(dataclasses.replace(s.tasks[0], brief="Do something else."),)
    ),
    "task-paths": lambda s: dataclasses.replace(
        s, tasks=(dataclasses.replace(s.tasks[0], paths=("rev.py", "extra.py")),)
    ),
    "check-description": lambda s: dataclasses.replace(
        s, checks=(dataclasses.replace(s.checks[0], description="always true"),)
    ),
}


@pytest.mark.parametrize("change", CHANGES.values(), ids=CHANGES)
def test_editing_the_term_sheet_after_approval_voids_it(tmp_path, change):
    checks, sheet = write_checks(tmp_path), sheet_of()
    event = approval_event(sheet, checks)
    require_approval([event], sheet, checks)
    with pytest.raises(NotApprovedError):
        require_approval([event], change(sheet), checks)


def test_accepted_risk_anyone_who_can_write_the_ledger_can_forge_approval(tmp_path):
    checks, sheet = write_checks(tmp_path), sheet_of()
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(approval_event(sheet, checks).to_json() + "\n")  # a hand-written line
    require_approval(read_events(ledger), sheet, checks)


# --- the round loop, with a scripted worker and the real gate --------------------------------


@dataclass
class Step:
    files: dict[str, str] = field(default_factory=dict)
    status: str | None = "continuing"
    outcome: Outcome = Outcome.COMPLETED
    cost: int | None = 1_000  # this slice's own spend; None = the CLI reported nothing
    after: object = None  # called after the files are written, to simulate outside interference


class Worker:
    def __init__(self, *steps: Step) -> None:
        self.steps, self.specs, self.totals = list(steps), [], {}

    def __call__(self, spec, workspace, log_path, *, env):
        self.specs.append(spec)
        step = self.steps.pop(0)
        for name, code in step.files.items():
            (workspace / name).write_text(code)
        if step.after:
            step.after()
        session = str(spec.session_id)
        if step.cost is not None:
            self.totals[session] = self.totals.get(session, 0) + step.cost
        cumulative = None if step.cost is None else self.totals[session]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("{}\n")
        status = None if step.status is None else {"status": step.status, "reason": "scripted"}
        return SliceRun(step.outcome, Usage(cumulative, 1, 1, 0), status, session, 0, 0.1, log_path)


def fund(tmp_path, worker, sheet=None, *, approved=None, corrupt_tail=False):
    """Run the loop. `approved` is the sheet the investor approved, if different from `sheet`."""
    sheet = sheet or sheet_of()
    paths = RunPaths(tmp_path / "run")
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(CHECK)
    with LedgerWriter(paths.ledger) as ledger:
        ledger.append(approval_event(approved or sheet, paths.checks))
        if corrupt_tail:
            with paths.ledger.open("a") as fh:
                fh.write('{"v": 1, "run": "r1", "rou')  # a torn line, as after a hard kill
        report = run_firm(
            sheet,
            paths,
            ledger,
            "r1",
            env={},
            config=FirmConfig(),
            ask=lambda _: "n",
            say=lambda _: None,
            slice_runner=worker,
            sleep=lambda _: None,
        )
    return report, read_events(paths.ledger), paths


def of(events, kind):
    return [e for e in events if e.event is kind]


def test_run_firm_refuses_a_sheet_changed_after_approval(tmp_path):
    approved = sheet_of()
    inflated = dataclasses.replace(approved, budget_micros=900_000, rounds=(Round(1, 900_000, 1),))
    worker = Worker(Step({"rev.py": RIGHT}))
    with pytest.raises(NotApprovedError):
        fund(tmp_path, worker, inflated, approved=approved)
    assert worker.specs == []


def test_a_worker_saying_done_is_not_a_pass(tmp_path):
    claims_done = Step({"rev.py": WRONG}, status="done")
    worker = Worker(*[claims_done] * 4)  # two workers, two stalled slices each
    report, events, _ = fund(tmp_path, worker)
    assert not report.all_passed and report.passed == 0
    assert {e.data["status"] for e in of(events, EventType.CHECK_RESULT)} == {"failed"}
    assert {e.data["status"]["status"] for e in of(events, EventType.SLICE_END)} == {"done"}
    assert len(of(events, EventType.SLICE_END)) == 4  # "done" did not end the task


def test_slices_of_unknown_cost_are_charged_at_their_cap_so_the_round_runs_out(tmp_path):
    sheet = dataclasses.replace(sheet_of(), budget_micros=320_000, rounds=(Round(1, 320_000, 1),))
    crashed = Step({"rev.py": WRONG}, status=None, outcome=Outcome.CRASHED, cost=None)
    worker = Worker(*[crashed] * 4)
    _, events, _ = fund(tmp_path, worker, sheet)
    ends = of(events, EventType.SLICE_END)
    # The ledger never invents a figure: both slices stay "unknown" and the total stays 0.
    assert [e.cost_micros for e in ends] == [None] * 3
    assert (total(events).cost_micros, total(events).unknown_cost_events) == (0, 3)
    # The budget treats each as spent at its cap, so the money stops the round with a step
    # still unplayed: caps of 100,000, 100,000 and the last 20,000 above the reserve.
    caps = [e.data["cap_micros"] for e in of(events, EventType.SLICE_START)]
    assert caps == [100_000, 100_000, 20_000]
    assert remaining(sheet, events, 1) == 100_000
    assert len(worker.specs) == 3


def test_an_overshooting_slice_is_recorded_and_ends_the_round(tmp_path):
    sheet = dataclasses.replace(sheet_of(), budget_micros=200_000, rounds=(Round(1, 200_000, 1),))
    worker = Worker(Step({"rev.py": WRONG}, cost=300_000), Step({"rev.py": RIGHT}))
    report, events, _ = fund(tmp_path, worker, sheet)
    assert [e.data["cap_micros"] for e in of(events, EventType.SLICE_START)] == [100_000]
    assert total(events).cost_micros == 300_000  # the overshoot is on the ledger, not hidden
    assert remaining(sheet, events, 1) == -100_000
    assert len(worker.specs) == 1 and not report.all_passed


def test_a_corrupt_ledger_stops_the_run_before_more_money_is_spent(tmp_path):
    worker = Worker(Step({"rev.py": WRONG}), Step({"rev.py": RIGHT}))
    with pytest.raises(LedgerCorruptError):
        fund(tmp_path, worker, corrupt_tail=True)
    assert worker.specs == []

    def garble():
        with (tmp_path / "run2" / "run" / "ledger.jsonl").open("a") as fh:
            fh.write("not json\n")

    worker = Worker(Step({"rev.py": WRONG}, after=garble), Step({"rev.py": RIGHT}))
    with pytest.raises(LedgerCorruptError):
        fund(tmp_path / "run2", worker)
    assert len(worker.specs) == 1  # the loop read the damaged ledger and stopped funding


# --- product assembly ------------------------------------------------------------------------


def test_product_assembly_skips_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("host secret")
    paths = RunPaths(tmp_path / "run")
    ws = paths.workspace("w1")
    ws.mkdir(parents=True)
    (ws / "rev.py").write_text(RIGHT)
    os.symlink(outside / "secret.txt", ws / "linked_file.txt")
    os.symlink(outside, ws / "linked_dir")
    state = RunState(
        workers={},
        tasks={"t1": TaskState("t1", ("w1",), "w1", frozenset({"c01"}), False)},
        closed_rounds=frozenset(),
        approved_rounds=frozenset(),
        stopped=False,
    )
    assemble_product(paths, sheet_of(), state)
    copied = sorted(p.relative_to(paths.product).as_posix() for p in paths.product.rglob("*"))
    assert copied == ["rev.py"]


def two_task_product(tmp_path, first: dict[str, str], second: dict[str, str], paths2=("up.py",)):
    sheet = TermSheet(
        "x",
        100_000,
        (Round(1, 100_000, 2),),
        (CheckSpec("c01", "d", "test_c01.py", "t1"), CheckSpec("c02", "d", "test_c02.py", "t2")),
        (Task("t1", "b", ("rev.py",)), Task("t2", "b", tuple(paths2))),
    )
    paths = RunPaths(tmp_path / "run")
    for worker, files in (("w1", first), ("w2", second)):
        for name, text in files.items():
            target = paths.workspace(worker) / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
    state = RunState(
        workers={},
        tasks={
            "t1": TaskState("t1", ("w1",), "w1", frozenset({"c01"}), False),
            "t2": TaskState("t2", ("w2",), "w2", frozenset({"c02"}), False),
        },
        closed_rounds=frozenset(),
        approved_rounds=frozenset(),
        stopped=False,
    )
    two_task_product.skipped = assemble_product(paths, sheet, state)
    return {
        p.relative_to(paths.product).as_posix(): p.read_text()
        for p in paths.product.rglob("*")
        if p.is_file()
    }


def test_a_worker_cannot_replace_a_file_another_task_owns(tmp_path):
    product = two_task_product(tmp_path, {"rev.py": RIGHT}, {"up.py": "UP", "rev.py": "CLOBBER"})
    assert product == {"rev.py": RIGHT, "up.py": "UP"}


def test_the_owner_wins_even_when_it_is_assembled_after_the_intruder(tmp_path):
    product = two_task_product(tmp_path, {"rev.py": RIGHT, "up.py": "CLOBBER"}, {"up.py": "UP"})
    assert product == {"rev.py": RIGHT, "up.py": "UP"}


def test_a_file_nobody_owns_comes_from_the_first_task_that_has_it(tmp_path):
    product = two_task_product(
        tmp_path,
        {"rev.py": RIGHT, "util.py": "FIRST"},
        {"up.py": "UP", "util.py": "SECOND", "extra.py": "ONLY"},
    )
    assert product == {"rev.py": RIGHT, "up.py": "UP", "util.py": "FIRST", "extra.py": "ONLY"}


def test_an_owned_folder_covers_everything_under_it(tmp_path):
    product = two_task_product(
        tmp_path,
        {"rev.py": RIGHT, "pkg/deep/mod.py": "CLOBBER"},
        {"pkg/deep/mod.py": "MINE", "pkg/__init__.py": ""},
        paths2=("pkg",),
    )
    assert product == {"rev.py": RIGHT, "pkg/deep/mod.py": "MINE", "pkg/__init__.py": ""}


def test_a_file_and_a_folder_of_the_same_name_do_not_crash_assembly(tmp_path):
    # Found by review: one worker's unowned file `x` and another's `x/y.py` raised out of the
    # run after all the work was done and paid for, leaving no report.
    product = two_task_product(
        tmp_path, {"rev.py": RIGHT, "x": "FILE"}, {"up.py": "UP", "x/y.py": "Y"}
    )
    assert product == {"rev.py": RIGHT, "up.py": "UP", "x": "FILE"}
    assert two_task_product.skipped == ["x/y.py"]
    product = two_task_product(
        tmp_path / "again", {"rev.py": RIGHT, "x/y.py": "Y"}, {"up.py": "UP", "x": "F"}
    )
    assert product == {"rev.py": RIGHT, "up.py": "UP", "x/y.py": "Y"}
    assert two_task_product.skipped == ["x"]


def test_agent_config_caches_and_old_attempts_never_reach_the_product(tmp_path):
    junk = {
        ".claude/settings.json": "{}",
        "sub/.claude/settings.json": "{}",
        "sub/.mcp.json": "{}",
        "__pycache__/rev.cpython-312.pyc": "x",
        "previous_attempt/rev.py": "OLD",
        "sub/kept.py": "KEPT",
    }
    product = two_task_product(tmp_path, {"rev.py": RIGHT, **junk}, {"up.py": "UP"})
    assert product == {"rev.py": RIGHT, "up.py": "UP", "sub/kept.py": "KEPT"}


# --- environment and model output at the trust boundaries ------------------------------------

FAKE_CLAUDE = f"""#!{sys.executable}
import json, os, sys
home = os.environ["HOME"]
with open(os.path.join(home, "env.log"), "a") as log:
    log.write(json.dumps(dict(os.environ)) + "\\n")
say = lambda e: print(json.dumps(e), flush=True)
result = {{"type": "result", "subtype": "success", "is_error": False, "session_id": "s-1",
          "terminal_reason": "completed", "modelUsage": {{}}, "total_cost_usd": 0.004}}
if sys.argv[sys.argv.index("--tools") + 1] == "":
    say({BOSS_INIT!r})
    draft = {{"tasks": [{{"id": "t1", "brief": "Create rev.py.", "paths": ["rev.py"]}}],
             "checks": [{{"description": "d", "task": "t1", "code": {CHECK!r}}}]}}
    say(result | {{"structured_output": draft}})
else:
    say({{"type": "system", "subtype": "init", "mcp_servers": [], "permissionMode": "dontAsk",
         "tools": ["Read", "Write", "Edit", "StructuredOutput"],
         "claude_code_version": "2.1.285"}})
    open("rev.py", "w").write({RIGHT!r})
    say(result | {{"structured_output": {{"status": "done", "reason": "ok"}}}})
"""


def test_callers_secrets_reach_neither_the_boss_call_nor_the_worker(tmp_path):
    from boss.cli import main

    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    (tmp_path / "project").mkdir()
    secrets = {
        "AWS_SECRET_ACCESS_KEY": "aws-secret-value",
        "GITHUB_TOKEN": "github-token-value",
        "OPENAI_API_KEY": "openai-key-value",
        "ANTHROPIC_BASE_URL": "http://proxy.invalid",
    }
    environ = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "BOSS_CLAUDE_BIN": str(fake),
        **secrets,
    }
    code = main(
        ["fund", "Reverse a string.", "--budget", "0.50", "--dir", str(tmp_path / "project")],
        ask=lambda _: "a",
        say=lambda _: None,
        environ=environ,
    )
    assert code == 0
    seen = [json.loads(line) for line in (tmp_path / "env.log").read_text().splitlines()]
    assert len(seen) == 2  # the boss's draft call and one worker slice
    # The interpreter and macOS add locale variables of their own to any child process.
    allowed = {"HOME", "PATH", "USER", "LANG", "TMPDIR", "CLAUDE_CONFIG_DIR"}
    allowed |= {"LC_CTYPE", "__CF_USER_TEXT_ENCODING"}
    for env in seen:
        assert set(env) <= allowed
        assert not set(secrets) & set(env)
        assert not set(secrets.values()) & set(env.values())


def test_the_boss_cannot_choose_ids_file_names_or_money(tmp_path):
    hostile = {
        "tasks": [{"id": "t1", "brief": "Create rev.py.", "paths": ["rev.py"], "budget": 1}],
        "checks": [
            {
                "description": "d",
                "task": "t1",
                "code": CHECK,
                "id": "../../evil",
                "file": "../evil.py",
            }
        ],
        "budget_micros": 10**12,
        "rounds": [{"n": 1, "budget_micros": 10**12, "unlock_checks": 1}],
    }
    result = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "terminal_reason": "completed",
        "total_cost_usd": 0.004,
        "modelUsage": {},
        "structured_output": hostile,
    }
    fake = tmp_path / "fake-claude"
    fake.write_text(
        f"#!{sys.executable}\nprint({json.dumps(BOSS_INIT)!r})\nprint({json.dumps(result)!r})\n"
    )
    fake.chmod(0o755)
    checks = tmp_path / "run" / "checks"
    draft = draft_term_sheet(
        "Reverse a string.",
        500_000,
        checks,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        executable=str(fake),
    )
    [check] = draft.sheet.checks
    assert (check.id, check.file) == ("c01", "test_c01.py")
    assert (draft.sheet.budget_micros, draft.sheet.rounds) == (500_000, (Round(1, 500_000, 1),))
    assert [p.name for p in checks.iterdir()] == ["test_c01.py"]
    assert not (tmp_path / "evil.py").exists()
