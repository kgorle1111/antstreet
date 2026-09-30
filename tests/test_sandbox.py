"""The sandbox command builder: exact text, hostile paths, tool detection. Runs anywhere."""

import sys
from pathlib import Path

import pytest

from boss import sandbox
from boss.sandbox import (
    Sandbox,
    SandboxMode,
    SandboxUnavailable,
    bwrap_argv,
    detect,
    missing_hint,
    python_readable,
    seatbelt_argv,
    seatbelt_profile,
    select,
)

PROFILE_NO_EXTRA = """\
(version 1)
(deny default)
(allow process-fork)
(allow process-exec)
(allow signal (target same-sandbox))
(allow sysctl-read)
(allow ipc-posix-sem)
(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))
(allow file-read-metadata)
(allow file-read*
  (literal "/")
  (literal "/dev/null")
  (subpath "/usr/share/locale")
  (subpath "/private/var/db/timezone")
  (subpath (param "WRITABLE")))
(allow file-write* (literal "/dev/null") (subpath (param "WRITABLE")))
"""
# Characters that would end a string, close a form or start a new one if pasted into profile text.
HOSTILE = ["a b", 'a"b', "a'b", "a(b)c)", "a\nb", "a\\b", '"))(allow default)((', "a;b", "é中"]


def test_profile_text_is_pinned():
    assert seatbelt_profile(0) == PROFILE_NO_EXTRA
    two = seatbelt_profile(2)
    assert two == PROFILE_NO_EXTRA.replace(
        '(subpath (param "WRITABLE")))\n(allow file-write*',
        '(subpath (param "WRITABLE"))\n  (subpath (param "R0"))\n  (subpath (param "R1")))\n'
        "(allow file-write*",
    )


def test_seatbelt_argv_is_pinned():
    argv = seatbelt_argv(
        "/usr/bin/sandbox-exec", ["/py", "-m", "pytest"],
        writable=Path("/w"), readable=[Path("/r0"), Path("/r1")],
    )  # fmt: skip
    assert argv == [
        "/usr/bin/sandbox-exec", "-D", "WRITABLE=/w", "-D", "R0=/r0", "-D", "R1=/r1",
        "-p", seatbelt_profile(2), "/py", "-m", "pytest",
    ]  # fmt: skip


@pytest.mark.parametrize("name", HOSTILE)
def test_a_hostile_path_never_reaches_the_profile_text(name):
    benign = seatbelt_argv("t", ["x"], writable=Path("/w"), readable=[Path("/r")])
    hostile = seatbelt_argv("t", ["x"], writable=Path(f"/w/{name}"), readable=[Path(f"/r/{name}")])
    profile = lambda argv: argv[argv.index("-p") + 1]  # noqa: E731
    assert profile(hostile) == profile(benign)
    assert f"WRITABLE=/w/{name}" in hostile and f"R0=/r/{name}" in hostile  # as data, one element


def test_bwrap_argv_is_pinned():
    argv = bwrap_argv(
        "/usr/bin/bwrap", ["/py", "-m", "pytest"],
        writable=Path("/tmp/run"), readable=[Path("/home/u/.venv"), Path("/usr")],
    )  # fmt: skip
    assert argv == [
        "/usr/bin/bwrap", "--die-with-parent", "--unshare-net", "--unshare-pid",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/home", "--tmpfs", "/root", "--tmpfs", "/tmp", "--tmpfs", "/run",
        "--ro-bind", "/home/u/.venv", "/home/u/.venv", "--ro-bind", "/usr", "/usr",
        "--bind", "/tmp/run", "/tmp/run", "--", "/py", "-m", "pytest",
    ]  # fmt: skip


@pytest.mark.parametrize("name", HOSTILE)
def test_bwrap_takes_a_hostile_path_as_one_argument(name):
    argv = bwrap_argv("b", ["x"], writable=Path(f"/w/{name}"), readable=[Path(f"/r/{name}")])
    assert argv.count(f"/w/{name}") == 2 and argv.count(f"/r/{name}") == 2


@pytest.mark.parametrize("build", [seatbelt_argv, bwrap_argv])
def test_relative_paths_are_refused_because_the_tool_would_read_them_from_the_wrong_place(build):
    with pytest.raises(ValueError, match="absolute"):
        build("t", ["x"], writable=Path("run"), readable=[])
    with pytest.raises(ValueError, match="absolute"):
        build("t", ["x"], writable=Path("/w"), readable=[Path("lib")])


@pytest.mark.parametrize("bad", [[], ["-p", "(allow default)"], ["--version"]])
def test_a_command_the_tool_would_read_as_an_option_is_refused(bad):
    with pytest.raises(ValueError, match="cannot sandbox"):
        Sandbox("sandbox-exec", "/x").wrap(bad, writable=Path("/w"), readable=[])


def test_wrap_picks_the_builder_by_tool_name():
    common = {"writable": Path("/w"), "readable": [Path("/r")]}
    mac = Sandbox("sandbox-exec", "/e").wrap(["c"], **common)
    linux = Sandbox("bwrap", "/e").wrap(["c"], **common)
    assert mac == seatbelt_argv("/e", ["c"], **common)
    assert linux == bwrap_argv("/e", ["c"], **common)


def test_python_readable_is_the_resolved_installation_and_environment():
    paths = python_readable()
    assert Path(sys.prefix).resolve() in paths and Path(sys.base_prefix).resolve() in paths
    assert all(p.is_absolute() and p.is_dir() for p in paths)
    assert list(paths) == sorted(set(paths))


# --- detection ------------------------------------------------------------------------------


def fake_tool(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)
    return path


@pytest.mark.parametrize(
    ("system", "name"), [("Darwin", "sandbox-exec"), ("Linux", "bwrap")], ids=["mac", "linux"]
)
def test_detect_finds_the_platforms_tool_on_the_given_path(tmp_path, system, name):
    tool = fake_tool(tmp_path / "bin", name, "exit 0")
    found = detect({"PATH": str(tmp_path / "bin")}, system=system)
    assert found == Sandbox(name, str(tool))


def test_detect_ignores_the_other_platforms_tool(tmp_path):
    fake_tool(tmp_path / "bin", "bwrap", "exit 0")
    assert detect({"PATH": str(tmp_path / "bin")}, system="Darwin") is None


def test_detect_returns_none_without_the_tool_or_a_path(tmp_path):
    (tmp_path / "bin").mkdir()
    assert detect({"PATH": str(tmp_path / "bin")}, system="Linux") is None
    assert detect({}, system="Linux") is None
    assert detect({"PATH": ""}, system="Linux") is None


def test_detect_returns_none_on_a_platform_with_no_tool(tmp_path):
    fake_tool(tmp_path / "bin", "sandbox-exec", "exit 0")
    assert detect({"PATH": str(tmp_path / "bin")}, system="Windows") is None


def test_a_tool_that_exists_but_fails_is_not_usable(tmp_path):
    fake_tool(tmp_path / "bin", "bwrap", "echo 'no user namespaces' >&2; exit 1")
    assert detect({"PATH": str(tmp_path / "bin")}, system="Linux") is None


def test_a_tool_that_cannot_be_started_is_not_usable(tmp_path):
    (tmp_path / "bin").mkdir()
    broken = tmp_path / "bin" / "bwrap"
    broken.write_text("#!/nonexistent/interpreter\n")
    broken.chmod(0o755)
    assert detect({"PATH": str(tmp_path / "bin")}, system="Linux") is None


def test_a_tool_that_hangs_is_not_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "_PROBE_TIMEOUT_S", 0.3)
    fake_tool(tmp_path / "bin", "bwrap", "exec sleep 5")
    assert detect({"PATH": str(tmp_path / "bin")}, system="Linux") is None


def test_the_probe_runs_the_interpreter_with_pytest_under_the_tool(tmp_path):
    log = tmp_path / "argv.log"
    fake_tool(tmp_path / "bin", "bwrap", f'printf "%s\\n" "$@" > {log}; exit 0')
    assert detect({"PATH": str(tmp_path / "bin")}, system="Linux") is not None
    lines = log.read_text().splitlines()
    assert lines[-5:] == [sys.executable, "-I", "-B", "-c", "import pytest"]
    assert "--unshare-net" in lines


# --- selecting by mode ----------------------------------------------------------------------


def test_off_never_looks_for_a_tool(monkeypatch):
    monkeypatch.setattr(sandbox, "detect", lambda *a, **k: pytest.fail("looked for a tool"))
    assert select(SandboxMode.OFF) is None


def test_auto_without_a_tool_is_none_and_require_without_a_tool_says_what_to_install(tmp_path):
    (tmp_path / "bin").mkdir()
    env = {"PATH": str(tmp_path / "bin")}
    assert select(SandboxMode.AUTO, env, system="Linux") is None
    with pytest.raises(SandboxUnavailable, match="bwrap") as excinfo:
        select(SandboxMode.REQUIRE, env, system="Linux")
    assert "install bubblewrap" in str(excinfo.value)
    assert "BOSS_GATE_SANDBOX=require" in str(excinfo.value)


@pytest.mark.parametrize("mode", [SandboxMode.AUTO, SandboxMode.REQUIRE])
def test_auto_and_require_return_the_tool_when_it_works(tmp_path, mode):
    tool = fake_tool(tmp_path / "bin", "bwrap", "exit 0")
    found = select(mode, {"PATH": str(tmp_path / "bin")}, system="Linux")
    assert found == Sandbox("bwrap", str(tool))


def test_missing_hints_name_the_tool_and_the_fix_per_platform():
    assert "install bubblewrap" in missing_hint("Linux")
    assert "sandbox-exec" in missing_hint("Darwin") and "macOS" in missing_hint("Darwin")
    assert "Windows" in missing_hint("Windows")
    assert missing_hint() == missing_hint(sandbox.platform.system())
