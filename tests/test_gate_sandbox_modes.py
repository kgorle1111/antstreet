"""How the gate chooses and applies a sandbox. No real sandbox needed: runs on every platform."""

from pathlib import Path

import pytest

from boss import gate as gate_module
from boss.gate import Check, CheckResult, CheckStatus, GateError, run_gate, sandbox_mode
from boss.sandbox import SandboxMode, python_readable

PASSING = "def test_ok():\n    assert True\n"
HANGING = "import time\ndef test_x():\n    time.sleep(60)\n"


@pytest.fixture
def dirs(tmp_path):
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    ws.mkdir()
    checks.mkdir()
    (checks / "test_c01.py").write_text(PASSING)
    return ws, checks


def gate(dirs, **kwargs):
    ws, checks = dirs
    return run_gate(ws, checks, [Check("c01", "test_c01.py")], **kwargs)


class Recorder:
    """A sandbox that confines nothing and remembers how it was asked to."""

    name = "recorder"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], Path, list[Path]]] = []

    def wrap(self, argv, *, writable, readable, hidden=()):
        self.calls.append((list(argv), writable, list(readable)))
        return list(argv)


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(gate_module, "select", lambda mode: rec)
    return rec


def test_unset_variable_means_auto():
    assert sandbox_mode({}) is SandboxMode.AUTO


@pytest.mark.parametrize(
    ("raw", "mode"),
    [
        ("auto", SandboxMode.AUTO),
        ("require", SandboxMode.REQUIRE),
        ("off", SandboxMode.OFF),
        (" OFF\n", SandboxMode.OFF),
        ("Require", SandboxMode.REQUIRE),
    ],
)
def test_variable_values(raw, mode):
    assert sandbox_mode({"BOSS_GATE_SANDBOX": raw}) is mode


@pytest.mark.parametrize("raw", ["", "on", "yes", "1", "sandbox-exec", "off;require"])
def test_any_other_value_is_a_gate_error_naming_the_variable_and_the_choices(raw):
    with pytest.raises(GateError, match=r"BOSS_GATE_SANDBOX.*auto\|require\|off"):
        sandbox_mode({"BOSS_GATE_SANDBOX": raw})


def test_run_gate_reads_the_variable_when_no_mode_is_passed(dirs, monkeypatch):
    seen = []
    monkeypatch.setattr(gate_module, "select", lambda mode: seen.append(mode))
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "require")
    gate(dirs)
    monkeypatch.delenv("BOSS_GATE_SANDBOX")
    gate(dirs)
    assert seen == [SandboxMode.REQUIRE, SandboxMode.AUTO]


def test_an_explicit_mode_beats_the_variable_and_the_variable_is_then_not_read(dirs, monkeypatch):
    seen = []
    monkeypatch.setattr(gate_module, "select", lambda mode: seen.append(mode))
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "not-a-mode")
    gate(dirs, sandbox=SandboxMode.OFF)
    assert seen == [SandboxMode.OFF]


def test_an_invalid_variable_stops_the_gate_before_any_check_runs(dirs, monkeypatch):
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "not-a-mode")
    with pytest.raises(GateError, match="BOSS_GATE_SANDBOX"):
        gate(dirs)
    with pytest.raises(GateError, match="BOSS_GATE_SANDBOX"):
        run_gate(dirs[0], dirs[1], [])


def no_tool_on_path(monkeypatch, tmp_path):
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))


def test_require_without_a_tool_is_a_gate_error_that_names_the_tool_and_the_fix(
    dirs, monkeypatch, tmp_path
):
    no_tool_on_path(monkeypatch, tmp_path)
    with pytest.raises(GateError, match=r"sandbox-exec|bwrap") as excinfo:
        gate(dirs, sandbox=SandboxMode.REQUIRE)
    assert "BOSS_GATE_SANDBOX=require" in str(excinfo.value)
    assert "macOS" in str(excinfo.value) or "install bubblewrap" in str(excinfo.value)


def test_require_is_set_from_the_environment_too(dirs, monkeypatch, tmp_path):
    no_tool_on_path(monkeypatch, tmp_path)
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "require")
    with pytest.raises(GateError, match="sandbox"):
        gate(dirs)


def test_auto_without_a_tool_runs_the_check_and_says_it_was_not_sandboxed(
    dirs, monkeypatch, tmp_path
):
    no_tool_on_path(monkeypatch, tmp_path)
    [result] = gate(dirs, sandbox=SandboxMode.AUTO)
    assert result.status is CheckStatus.PASSED and result.sandboxed is False


def test_off_never_looks_for_a_tool(dirs, monkeypatch):
    monkeypatch.setattr("boss.sandbox.detect", lambda *a, **k: pytest.fail("looked for a tool"))
    [result] = gate(dirs, sandbox=SandboxMode.OFF)
    assert result.status is CheckStatus.PASSED and result.sandboxed is False


def test_with_no_checks_nothing_is_required_of_the_machine(dirs, monkeypatch, tmp_path):
    no_tool_on_path(monkeypatch, tmp_path)
    assert run_gate(dirs[0], dirs[1], [], sandbox=SandboxMode.REQUIRE) == []


def test_a_sandbox_wraps_the_pytest_command_with_the_run_folder_writable(dirs, recorder):
    [result] = gate(dirs)
    [(argv, writable, readable)] = recorder.calls
    assert result.status is CheckStatus.PASSED and result.sandboxed is True
    assert argv[1:4] == ["-I", "-B", "-c"]
    assert writable.name.startswith("boss_gate_") and writable == writable.resolve()
    assert readable == list(python_readable())
    assert argv[6] == ""  # no repo site-packages unless one is passed
    assert Path(argv[7]).resolve().is_relative_to(writable)  # the copied check is inside it


def test_every_check_gets_its_own_folder_and_every_result_says_it_was_sandboxed(dirs, recorder):
    (dirs[1] / "test_c02.py").write_text(PASSING)
    results = run_gate(dirs[0], dirs[1], [Check("c01", "test_c01.py"), Check("c02", "test_c02.py")])
    assert [r.sandboxed for r in results] == [True, True]
    assert len({call[1] for call in recorder.calls}) == 2


def test_failed_and_timed_out_results_carry_the_flag_too(dirs, recorder):
    (dirs[1] / "test_c01.py").write_text("def test_x():\n    assert False\n")
    [failed] = gate(dirs)
    (dirs[1] / "test_c01.py").write_text(HANGING)
    [slow] = gate(dirs, timeout_s=1.0)
    assert (failed.status, failed.sandboxed) == (CheckStatus.FAILED, True)
    assert (slow.status, slow.sandboxed) == (CheckStatus.TIMEOUT, True)


def test_existing_constructors_keep_working_and_default_to_unsandboxed():
    result = CheckResult("c01", CheckStatus.PASSED, 0, "1 passed", "", 0.1)
    assert result.sandboxed is False
