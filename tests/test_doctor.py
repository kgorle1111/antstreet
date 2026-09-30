"""Doctor tests against a fake CLI: every check and every fix line, with no model calls."""

import json
import os
import sys
from pathlib import Path

import pytest

from boss.doctor import DoctorCheck, render_doctor, run_doctor

FAKE_CLI = f"""#!{sys.executable}
import os, sys
if sys.argv[1] == "--version":
    print(os.environ["FAKE_VERSION"])
elif sys.argv[1:3] == ["auth", "status"]:
    print(os.environ["FAKE_AUTH_JSON"])
else:
    open(os.environ["FAKE_ARGV_LOG"], "w").write("\\n".join(sys.argv[1:]))
    print(os.environ["FAKE_RESULT_JSON"])
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""
OK_RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
}
LOGIN_FAILURE = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "api_error_status": 401,
    "terminal_reason": "api_error",
    "total_cost_usd": 0,
    "modelUsage": {},
}
NAMES = [
    "python",
    "platform",
    "pytest",
    "claude cli",
    "claude version",
    "login",
    "writable folder",
    "gate sandbox",
]


@pytest.fixture
def cli(tmp_path: Path) -> str:
    path = tmp_path / "fake-claude"
    path.write_text(FAKE_CLI)
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {
        "FAKE_VERSION": "2.1.285 (Claude Code)",
        "FAKE_AUTH_JSON": json.dumps({"loggedIn": True}),
        "FAKE_RESULT_JSON": json.dumps(OK_RESULT),
        "FAKE_ARGV_LOG": str(tmp_path / "argv.log"),
    }


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


def by_name(checks: list[DoctorCheck]) -> dict[str, DoctorCheck]:
    assert [c.name for c in checks] == NAMES
    return {c.name: c for c in checks}


def test_all_ok(cli, env, cwd):
    checks = by_name(run_doctor(env, cwd, executable=cli))
    assert all(c.ok and c.fix == "" for c in checks.values())
    assert "2.1.285" in checks["claude version"].detail
    assert (cwd / ".boss").is_dir()
    assert list((cwd / ".boss").iterdir()) == []  # probe file removed, directory kept


def test_missing_binary_skips_dependents(tmp_path, env, cwd):
    checks = by_name(run_doctor(env, cwd, executable=str(tmp_path / "nope")))
    assert not checks["claude cli"].ok and "install Claude Code" in checks["claude cli"].fix
    for name in ("claude version", "login"):
        assert not checks[name].ok
        assert checks[name].detail.startswith("skipped")
        assert "claude cli" in checks[name].detail
    assert checks["writable folder"].ok


def test_bare_name_is_looked_up_on_env_path(tmp_path, cli, env, cwd):
    env["PATH"] = str(tmp_path)
    checks = by_name(run_doctor(env, cwd, executable="fake-claude"))
    assert checks["claude cli"].ok and checks["claude version"].ok


def test_version_too_old(cli, env, cwd):
    env["FAKE_VERSION"] = "2.1.178 (Claude Code)"
    check = by_name(run_doctor(env, cwd, executable=cli))["claude version"]
    assert not check.ok
    assert "2.1.178" in check.detail and "2.1.277" in check.detail
    assert "claude update" in check.fix


def test_unparsable_version(cli, env, cwd):
    env["FAKE_VERSION"] = "not a version"
    check = by_name(run_doctor(env, cwd, executable=cli))["claude version"]
    assert not check.ok and "unparsable" in check.detail and check.fix


def test_version_nonzero_exit_fails(cli, env, cwd):
    env["FAKE_EXIT"] = "3"
    check = by_name(run_doctor(env, cwd, executable=cli))["claude version"]
    assert not check.ok and "exit 3" in check.detail


def test_not_logged_in(cli, env, cwd):
    env["FAKE_AUTH_JSON"] = json.dumps({"loggedIn": False})
    check = by_name(run_doctor(env, cwd, executable=cli))["login"]
    assert not check.ok and check.fix == "claude auth login"


def test_unparsable_auth_status(cli, env, cwd):
    env["FAKE_AUTH_JSON"] = "garbage"
    check = by_name(run_doctor(env, cwd, executable=cli))["login"]
    assert not check.ok and "unparsable" in check.detail and check.fix == "claude auth login"


def test_logged_in_without_live_is_reported_not_verified(cli, env, cwd):
    check = by_name(run_doctor(env, cwd, executable=cli))["login"]
    assert check.ok
    assert "reported, not verified" in check.detail and "boss doctor --live" in check.detail
    assert not Path(env["FAKE_ARGV_LOG"]).exists()  # no live call was made


def test_live_completed_is_verified(cli, env, cwd):
    check = by_name(run_doctor(env, cwd, live=True, executable=cli))["login"]
    assert check.ok and "verified with one live call" in check.detail
    argv = Path(env["FAKE_ARGV_LOG"]).read_text().split("\n")
    assert "--safe-mode" in argv and "--bare" not in argv
    assert argv[argv.index("--model") + 1] == "haiku"


def test_live_login_failure(cli, env, cwd):
    env["FAKE_RESULT_JSON"] = json.dumps(LOGIN_FAILURE)
    check = by_name(run_doctor(env, cwd, live=True, executable=cli))["login"]
    assert not check.ok and check.fix == "claude auth login"


def test_live_other_outcome_names_it(cli, env, cwd):
    env["FAKE_RESULT_JSON"] = "not json at all"
    check = by_name(run_doctor(env, cwd, live=True, executable=cli))["login"]
    assert not check.ok and "CRASHED" in check.detail and check.fix


def test_live_skips_call_when_not_logged_in(cli, env, cwd):
    env["FAKE_AUTH_JSON"] = json.dumps({"loggedIn": False})
    check = by_name(run_doctor(env, cwd, live=True, executable=cli))["login"]
    assert not check.ok and not Path(env["FAKE_ARGV_LOG"]).exists()


def test_api_key_path(cli, env, cwd):
    env["ANTHROPIC_API_KEY"] = "sk-ant-test-value"
    env["FAKE_AUTH_JSON"] = json.dumps({"loggedIn": False})  # must not be consulted
    check = by_name(run_doctor(env, cwd, executable=cli))["login"]
    assert check.ok and "API key" in check.detail and "not been verified" in check.detail
    assert "sk-ant-test-value" not in check.detail


def test_api_key_live_uses_bare(cli, env, cwd):
    env["ANTHROPIC_API_KEY"] = "sk-ant-test-value"
    check = by_name(run_doctor(env, cwd, live=True, executable=cli))["login"]
    assert check.ok
    argv = Path(env["FAKE_ARGV_LOG"]).read_text().split("\n")
    assert "--bare" in argv and "--safe-mode" not in argv


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_unwritable_cwd(cli, env, tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        check = by_name(run_doctor(env, locked, executable=cli))["writable folder"]
    finally:
        locked.chmod(0o700)
    assert not check.ok and "chmod u+w" in check.fix and not (locked / ".boss").exists()


def test_render_lists_a_fix_for_each_failure_and_a_summary():
    checks = [
        DoctorCheck("python", True, "3.12.4", ""),
        DoctorCheck("claude cli", False, "'claude' not found", "install Claude Code"),
        DoctorCheck("login", False, "not logged in", "claude auth login"),
        DoctorCheck("pytest", True, "importable", ""),
        DoctorCheck("platform", True, "posix", ""),
        DoctorCheck("claude version", True, "2.1.285", ""),
        DoctorCheck("writable folder", True, "/x/.boss", ""),
    ]
    lines = render_doctor(checks).splitlines()
    assert lines[0] == "ok    python: 3.12.4"
    assert "FAIL  claude cli: 'claude' not found" in lines
    assert "fix: install Claude Code" in lines[2]
    assert "fix: claude auth login" in lines[4]
    assert lines[-1] == "2 of 7 checks failed"
    assert sum("fix:" in line for line in lines) == 2


def test_render_all_ok_has_no_fix_lines():
    text = render_doctor([DoctorCheck("python", True, "3.12", "")])
    assert "fix:" not in text and text.endswith("all 1 checks ok")
