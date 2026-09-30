"""The doctor's gate sandbox line: a warning when there is none, a failure only when required."""

import platform
import sys
from pathlib import Path

import pytest

from boss import doctor
from boss.doctor import DoctorCheck, render_doctor, run_doctor
from boss.sandbox import Sandbox, detect

FAKE_CLI = f"""#!{sys.executable}
import sys
if sys.argv[1] == "--version":
    print("2.1.285 (Claude Code)")
elif sys.argv[1:3] == ["auth", "status"]:
    print('{{"loggedIn": true}}')
"""


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("BOSS_GATE_SANDBOX", raising=False)


@pytest.fixture
def cli(tmp_path: Path) -> str:
    path = tmp_path / "fake-claude"
    path.write_text(FAKE_CLI)
    path.chmod(0o755)
    return str(path)


def sandbox_line(tmp_path: Path, cli: str) -> DoctorCheck:
    cwd = tmp_path / "work"
    cwd.mkdir(exist_ok=True)
    checks = run_doctor({}, cwd, executable=cli)
    assert checks[-1].name == "gate sandbox"
    return checks[-1]


def no_tool(monkeypatch, system="Linux"):
    monkeypatch.setattr(doctor, "detect", lambda: None)
    monkeypatch.setattr(platform, "system", lambda: system)


def test_a_working_tool_is_named(monkeypatch, tmp_path, cli):
    monkeypatch.setattr(doctor, "detect", lambda: Sandbox("bwrap", "/usr/bin/bwrap"))
    check = sandbox_line(tmp_path, cli)
    assert check.ok and check.fix == "" and check.advice == ""
    assert check.detail.startswith("bwrap:") and "no network" in check.detail


def test_no_tool_is_a_warning_with_the_fix_and_does_not_fail_the_run(monkeypatch, tmp_path, cli):
    no_tool(monkeypatch)
    cwd = tmp_path / "work"
    cwd.mkdir()
    checks = run_doctor({}, cwd, executable=cli)
    assert all(c.ok for c in checks)  # `boss doctor` exits 0 iff every check is ok
    check = checks[-1]
    assert check.fix == "" and "install bubblewrap" in check.advice
    assert "full access" in check.detail
    text = render_doctor(checks)
    assert "WARN  gate sandbox: none available" in text
    assert "        fix: " + check.advice in text
    assert text.splitlines()[-1] == f"all {len(checks)} checks ok (1 warning)"


def test_macos_without_a_working_tool_gets_a_macos_hint(monkeypatch, tmp_path, cli):
    no_tool(monkeypatch, "Darwin")
    check = sandbox_line(tmp_path, cli)
    assert check.ok and "sandbox-exec" in check.advice


def test_require_without_a_tool_fails_with_the_fix(monkeypatch, tmp_path, cli):
    no_tool(monkeypatch)
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "require")
    check = sandbox_line(tmp_path, cli)
    assert not check.ok
    assert "BOSS_GATE_SANDBOX=require" in check.detail and "install bubblewrap" in check.fix


def test_require_with_a_tool_is_fine(monkeypatch, tmp_path, cli):
    monkeypatch.setattr(doctor, "detect", lambda: Sandbox("sandbox-exec", "/usr/bin/sandbox-exec"))
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "require")
    assert sandbox_line(tmp_path, cli).ok


def test_off_is_reported_as_chosen_and_never_looks_for_a_tool(monkeypatch, tmp_path, cli):
    monkeypatch.setattr(doctor, "detect", lambda: pytest.fail("looked for a tool"))
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "off")
    check = sandbox_line(tmp_path, cli)
    assert check.ok and check.advice == "" and check.detail.startswith("off")


def test_a_bad_value_fails_the_line_and_names_the_variable(monkeypatch, tmp_path, cli):
    monkeypatch.setenv("BOSS_GATE_SANDBOX", "maybe")
    check = sandbox_line(tmp_path, cli)
    assert not check.ok
    assert "BOSS_GATE_SANDBOX" in check.detail and "unset" in check.fix


def test_the_real_machine_reports_what_detect_finds(tmp_path, cli):
    found = detect()
    check = sandbox_line(tmp_path, cli)
    assert check.ok
    assert (found.name in check.detail) if found else check.advice


def test_warnings_are_counted_and_do_not_read_as_failures():
    warn = DoctorCheck("a", True, "d", "", "do this")
    lines = render_doctor([warn, DoctorCheck("b", True, "d", ""), warn]).splitlines()
    assert lines[0] == "WARN  a: d" and lines[1] == "        fix: do this"
    assert lines[2] == "ok    b: d"
    assert lines[-1] == "all 3 checks ok (2 warnings)"


def test_failures_and_warnings_are_both_counted():
    checks = [DoctorCheck("a", True, "d", "", "w"), DoctorCheck("b", False, "d", "f")]
    assert render_doctor(checks).splitlines()[-1] == "1 of 2 checks failed (1 warning)"
