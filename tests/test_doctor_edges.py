"""Doctor edge cases: unrunnable or hanging binaries, old runtimes and hostile status output."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from boss import doctor
from boss.doctor import run_doctor

FAKE_CLI = f"""#!{sys.executable}
import json, os, sys
if sys.argv[1] == "--version":
    open(os.environ["FAKE_ENV_LOG"], "w").write(json.dumps(sorted(os.environ)))
    print(os.environ.get("FAKE_VERSION", "2.1.285 (Claude Code)"))
elif sys.argv[1:3] == ["auth", "status"]:
    print(os.environ.get("FAKE_AUTH_OUT", '{{"loggedIn": true}}'))
else:
    print(os.environ.get("FAKE_RESULT_JSON", "{{}}"))
"""
OK_RESULT = {"type": "result", "subtype": "success", "is_error": False}


@pytest.fixture
def cli(tmp_path: Path) -> str:
    path = tmp_path / "fake-claude"
    path.write_text(FAKE_CLI)
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"FAKE_ENV_LOG": str(tmp_path / "env.log"), "FAKE_RESULT_JSON": json.dumps(OK_RESULT)}


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


def check(checks, name):
    [found] = [c for c in checks if c.name == name]
    return found


def hang_on(monkeypatch, marker: str, exc: BaseException):
    """Make any subprocess whose argv contains `marker` raise `exc`; run the rest for real."""
    real = subprocess.run

    def fake(argv, *args, **kwargs):
        if marker in argv:
            raise exc
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(doctor.subprocess, "run", fake)


# --- the interpreter and platform checks ----------------------------------------------------


def test_old_python_fails_with_the_found_version_and_a_fix(cli, env, cwd, monkeypatch):
    monkeypatch.setattr(doctor, "sys", SimpleNamespace(version_info=(3, 11, 4, "final", 0)))
    found = check(run_doctor(env, cwd, executable=cli), "python")
    assert (found.ok, found.detail, found.fix) == (
        False,
        "3.11.4, need 3.12 or newer",
        "run boss with Python 3.12+",
    )


def test_python_3_12_exactly_passes(cli, env, cwd, monkeypatch):
    monkeypatch.setattr(doctor, "sys", SimpleNamespace(version_info=(3, 12, 0, "final", 0)))
    found = check(run_doctor(env, cwd, executable=cli), "python")
    assert (found.ok, found.detail) == (True, "3.12.0")


def test_non_posix_platform_fails_with_its_name(cli, env, cwd, monkeypatch):
    monkeypatch.setattr(doctor, "os", SimpleNamespace(name="nt", getpid=os.getpid))
    found = check(run_doctor(env, cwd, executable=cli), "platform")
    assert (found.ok, found.detail) == (False, "nt is unsupported")
    assert found.fix == "run boss on macOS or Linux"


def test_missing_pytest_fails_and_says_why(cli, env, cwd, monkeypatch):
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name == "pytest" else real(name, *a)
    )
    found = check(run_doctor(env, cwd, executable=cli), "pytest")
    assert not found.ok
    assert found.detail == "not importable; the gate runs checks with it"
    assert found.fix == "reinstall boss"


# --- binaries that cannot run or hang --------------------------------------------------------


def test_a_binary_with_a_dead_interpreter_is_a_failed_check_not_an_exception(tmp_path, env, cwd):
    broken = tmp_path / "broken-claude"
    broken.write_text("#!/nonexistent/interpreter\n")
    broken.chmod(0o755)
    checks = run_doctor(env, cwd, executable=str(broken))
    assert check(checks, "claude cli").ok
    version = check(checks, "claude version")
    assert (version.ok, version.detail) == (False, "--version could not run: FileNotFoundError")
    login = check(checks, "login")
    assert (login.ok, login.detail) == (False, "auth status could not run: FileNotFoundError")
    assert login.fix == "claude auth login"


def test_a_hanging_version_probe_times_out_with_its_limit(cli, env, cwd, monkeypatch):
    hang_on(monkeypatch, "--version", subprocess.TimeoutExpired("claude", 20))
    version = check(run_doctor(env, cwd, executable=cli), "claude version")
    assert (version.ok, version.detail) == (False, "--version timed out after 20s")
    assert "update Claude Code to 2.1.277 or newer" in version.fix


def test_a_hanging_auth_status_is_a_failed_login_with_a_fix(cli, env, cwd, monkeypatch):
    hang_on(monkeypatch, "auth", subprocess.TimeoutExpired("claude", 20))
    login = check(run_doctor(env, cwd, executable=cli), "login")
    assert (login.ok, login.detail, login.fix) == (
        False,
        "auth status timed out after 20s",
        "claude auth login",
    )


def test_a_hanging_live_call_points_at_the_network(cli, env, cwd, monkeypatch):
    hang_on(monkeypatch, "--print", subprocess.TimeoutExpired("claude", 120))
    login = check(run_doctor(env, cwd, live=True, executable=cli), "login")
    assert (login.ok, login.detail) == (False, "live call timed out after 120s")
    assert login.fix == "check your network, then re-run with --live"


def test_a_value_error_from_the_os_is_reported_by_class_name(cli, env, cwd, monkeypatch):
    hang_on(monkeypatch, "--version", ValueError("embedded null byte"))
    version = check(run_doctor(env, cwd, executable=cli), "claude version")
    assert version.detail == "--version could not run: ValueError"


def test_the_probe_timeout_constants_are_what_the_messages_report(cli, env, cwd, monkeypatch):
    seen = []
    real = subprocess.run

    def spy(argv, *args, **kwargs):
        seen.append((argv[1], kwargs["timeout"]))
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(doctor.subprocess, "run", spy)
    run_doctor(env, cwd, live=True, executable=cli)
    assert seen == [("--version", 20), ("auth", 20), ("--print", 120)]


def test_the_binary_sees_only_the_env_it_was_given(cli, env, cwd, monkeypatch):
    monkeypatch.setenv("BOSS_TEST_SECRET_TOKEN", "leaky")
    run_doctor(env, cwd, executable=cli)
    seen = json.loads(Path(env["FAKE_ENV_LOG"]).read_text())
    assert "BOSS_TEST_SECRET_TOKEN" not in seen
    assert {"FAKE_ENV_LOG", "FAKE_RESULT_JSON"} <= set(seen)


# --- versions and auth output ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("2.1.277 (Claude Code)", True),
        ("2.1.276 (Claude Code)", False),
        ("2.2.0", True),
        ("3.0.0", True),
        ("2.1.9", False),
        ("2.1.1000", True),
        ("v2.1.285", False),
        ("", False),
    ],
)
def test_minimum_version_boundaries(cli, env, cwd, text, ok):
    env["FAKE_VERSION"] = text
    assert check(run_doctor(env, cwd, executable=cli), "claude version").ok is ok


@pytest.mark.parametrize(
    "out",
    ['{"loggedIn": "yes"}', '{"loggedIn": 1}', "[true]", "null", '{"other": true}', "", "{"],
)
def test_auth_status_that_is_not_a_boolean_flag_is_unparsable_not_a_guess(cli, env, cwd, out):
    env["FAKE_AUTH_OUT"] = out
    login = check(run_doctor(env, cwd, executable=cli), "login")
    assert not login.ok
    assert login.detail == "auth status gave unparsable output (exit 0)"


def test_logged_in_true_is_reported_but_not_verified(cli, env, cwd):
    login = check(run_doctor(env, cwd, executable=cli), "login")
    assert login.ok
    assert "reported, not verified" in login.detail


def test_an_empty_api_key_value_counts_as_no_api_key(cli, env, cwd):
    env["ANTHROPIC_API_KEY"] = ""
    env["FAKE_AUTH_OUT"] = json.dumps({"loggedIn": False})
    login = check(run_doctor(env, cwd, executable=cli), "login")
    assert (login.ok, login.detail) == (False, "not logged in")


def test_a_live_call_is_not_made_for_an_unparsable_status(cli, env, cwd):
    env["FAKE_AUTH_OUT"] = "garbage"
    login = check(run_doctor(env, cwd, live=True, executable=cli), "login")
    assert login.detail.startswith("auth status gave unparsable output")


# --- the writable-folder probe ---------------------------------------------------------------


def test_a_missing_working_directory_fails_the_folder_check(cli, env, tmp_path):
    found = check(run_doctor(env, tmp_path / "does-not-exist", executable=cli), "writable folder")
    assert not found.ok
    assert found.detail == f"{tmp_path / 'does-not-exist' / '.boss'}: FileNotFoundError"
    assert "chmod u+w" in found.fix


def test_a_file_named_dot_boss_fails_the_folder_check(cli, env, cwd):
    (cwd / ".boss").write_text("not a directory")
    found = check(run_doctor(env, cwd, executable=cli), "writable folder")
    assert not found.ok
    assert found.detail.endswith(".boss: FileExistsError")
    assert (cwd / ".boss").read_text() == "not a directory"


def test_an_existing_dot_boss_folder_keeps_its_contents(cli, env, cwd):
    (cwd / ".boss").mkdir()
    (cwd / ".boss" / "runs.txt").write_text("keep")
    assert check(run_doctor(env, cwd, executable=cli), "writable folder").ok
    assert [p.name for p in (cwd / ".boss").iterdir()] == ["runs.txt"]


def test_every_check_is_always_reported_even_when_all_of_them_fail(tmp_path, env, monkeypatch):
    monkeypatch.setattr(doctor, "sys", SimpleNamespace(version_info=(3, 9, 0, "final", 0)))
    checks = run_doctor(env, tmp_path / "nope", executable=str(tmp_path / "missing"))
    assert [c.name for c in checks] == [
        "python",
        "platform",
        "pytest",
        "claude cli",
        "claude version",
        "login",
        "writable folder",
        "gate sandbox",
    ]
    assert [c.ok for c in checks] == [False, True, True, False, False, False, False, True]
    assert all(c.fix for c in checks if not c.ok)
