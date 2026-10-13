"""`antstreet doctor --mods` against a fake `claude plugin`: what it flags, and that it never says
"no mods" when it could not look. The JSON shapes are those Claude Code 2.1.296 printed in a
throwaway HOME (an inert `skills-dir` plugin, and one whose module hooks tool.call and tool.check).
"""

import json
import sys
from pathlib import Path

import pytest

from antstreet import cli as antstreet_cli
from antstreet import doctor
from antstreet.doctor import DoctorCheck, render_doctor, run_doctor

FAKE_CLI = f"""#!{sys.executable}
import json, os, sys, time
argv = sys.argv[1:]
cfg = json.load(open(os.path.join(os.path.dirname(sys.argv[0]), "fake.json")))
if argv == ["--version"]:
    print("2.1.296 (Claude Code)")
elif argv[:2] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True}}))
elif argv[:3] == ["plugin", "list", "--json"]:
    open(cfg["FAKE_CWD_LOG"], "w").write(os.getcwd())
    time.sleep(float(cfg.get("FAKE_SLEEP", "0")))
    print(cfg["FAKE_LIST"])
elif argv[:3] == ["plugin", "validate", "--json"]:
    reports = json.loads(cfg["FAKE_REPORTS"])
    print(json.dumps(reports[argv[3]]) if argv[3] in reports else "not json")
    sys.exit(0 if argv[3] in reports else 1)
else:
    sys.exit(9)
"""


def report(*hooks: str, path: str = "/p/hooks/hooks.json", success: bool = True) -> dict:
    """The shape `claude plugin validate --json` printed for a plugin with these gating hooks."""
    gating = [
        {"module": "./register.ts", "pattern": h, "hook": h, "hasCatch": False} for h in hooks
    ]
    contents = [{"file": path, "type": "hooks", "errors": [], "gatingHooks": gating}]
    manifest = {"type": "plugin", "errors": [], "warnings": [], "notes": [], "gatingHooks": []}
    return {"success": success, "strict": False, "manifest": manifest, "contents": contents}


def entry(plugin_id: str, path: str, *, scope: str = "user", enabled: bool = True) -> dict:
    return {
        "id": plugin_id,
        "version": "0.1.0",
        "scope": scope,
        "enabled": enabled,
        "installPath": path,
    }


SUPPRESSED = {  # the entry printed for an untrusted workspace's ./.claude/skills/ folder
    "id": "(suppressed)@skills-dir",
    "version": "unknown",
    "scope": "project",
    "enabled": False,
    "installPath": "",
    "notes": ["1 project-scope directory ... was skipped because this workspace was not trusted"],
    "noteDetails": [{"type": "project-scope-suppressed-untrusted"}],
}


@pytest.fixture
def cli(tmp_path: Path) -> str:
    path = tmp_path / "fake-claude"
    path.write_text(FAKE_CLI)
    path.chmod(0o755)
    return str(path)


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    return {"FAKE_LIST": "[]", "FAKE_REPORTS": "{}", "FAKE_CWD_LOG": str(tmp_path / "cwd.log")}


def configure(env: dict[str, str], cli: str) -> None:
    """Hand the fake its answers in a file beside it: the CLI passes only allowlisted variables."""
    Path(cli).with_name("fake.json").write_text(json.dumps(env))


def run(env: dict[str, str], cwd: Path, *, executable: str, **flags: bool) -> list[DoctorCheck]:
    configure(env, executable)
    return run_doctor(env, cwd, executable=executable, **flags)


def mods(checks: list[DoctorCheck]) -> list[DoctorCheck]:
    return [c for c in checks if c.name == "mods" or c.name.startswith("mod ")]


def test_without_the_flag_no_plugin_command_runs(cli, env, cwd):
    assert mods(run(env, cwd, executable=cli)) == []
    assert not Path(env["FAKE_CWD_LOG"]).exists()


def test_a_clean_machine_passes_and_says_what_was_inspected(cli, env, cwd):
    env["FAKE_LIST"] = json.dumps([entry("helper@official", "/m/helper"), entry("x@builtin", "")])
    env["FAKE_REPORTS"] = json.dumps({"/m/helper": report()})
    found = mods(run(env, cwd, mods=True, executable=cli))
    assert [(c.name, c.ok, c.advice) for c in found] == [("mods", True, "")]
    assert found[0].detail == "2 plugins listed and inspected"
    assert Path(env["FAKE_CWD_LOG"]).read_text() == str(cwd.resolve())  # project scope is read


def test_a_skills_dir_plugin_with_gating_hooks_fails_and_names_its_path(cli, env, cwd):
    path = "/home/u/.claude/skills/gatemod"
    env["FAKE_LIST"] = json.dumps([entry("gatemod@skills-dir", path)])
    env["FAKE_REPORTS"] = json.dumps({path: report("tool.call", "tool.check")})
    checks = run(env, cwd, mods=True, executable=cli)
    check = {c.name: c for c in checks}["mod gatemod@skills-dir"]
    assert not check.ok
    assert path in check.detail and "tool.call, tool.check" in check.detail
    assert "guard" in check.detail and f"delete {path}" in check.fix
    assert antstreet_cli.EXIT_FAILED == 1 and not all(c.ok for c in checks)


def test_a_skills_dir_plugin_without_gating_hooks_is_a_warning_with_its_path(cli, env, cwd):
    path = "/w/.claude/skills/inertproj"
    env["FAKE_LIST"] = json.dumps([entry("inertproj@skills-dir", path, scope="project")])
    env["FAKE_REPORTS"] = json.dumps({path: report()})
    check = mods(run(env, cwd, mods=True, executable=cli))[1]
    assert check.ok and check.advice and path in check.detail and "no gating hooks" in check.detail


def test_a_marketplace_plugin_with_a_gating_hook_is_a_warning(cli, env, cwd):
    env["FAKE_LIST"] = json.dumps([entry("guardian@market", "/m/g")])
    env["FAKE_REPORTS"] = json.dumps({"/m/g": report("tool.check")})
    check = mods(run(env, cwd, mods=True, executable=cli))[1]
    assert check.ok and "tool.check" in check.detail and "claude plugin disable" in check.advice


def test_a_suppressed_project_folder_is_a_warning_not_silence(cli, env, cwd):
    env["FAKE_LIST"] = json.dumps([SUPPRESSED])
    check = mods(run(env, cwd, mods=True, executable=cli))[1]
    assert check.ok and "not loaded now" in check.detail and "trusted" in check.advice
    assert "project scope, a folder under ./.claude/skills/" in check.detail
    assert "skipped because" not in render_doctor([check])  # the CLI's own text is never shown


@pytest.mark.parametrize(
    ("listing", "said"),
    [
        ("not json", "unparsable"),
        ('{"plugins": []}', "unexpected shape"),
        ('[{"name": "no id"}]', "unexpected shape"),
    ],
)
def test_unparsable_or_odd_list_output_fails_and_never_reads_as_clean(cli, env, cwd, listing, said):
    env["FAKE_LIST"] = listing
    found = mods(run(env, cwd, mods=True, executable=cli))
    assert len(found) == 1 and not found[0].ok and said in found[0].detail
    assert "claude plugin list --json" in found[0].fix and "re-run" in found[0].fix


def test_a_plugin_that_cannot_be_validated_fails(cli, env, cwd):
    env["FAKE_LIST"] = json.dumps([entry("a@skills-dir", "/s/a"), entry("b@m", "/m/b")])
    env["FAKE_REPORTS"] = json.dumps({"/m/b": report(success=False)})
    a, b = mods(run(env, cwd, mods=True, executable=cli))[1:]
    assert not a.ok and "could not inspect /s/a" in a.detail and "unparsable" in a.detail
    assert not b.ok and "may not all be listed" in b.detail
    assert "claude plugin validate /s/a" in a.fix


def test_a_timeout_fails_with_the_next_step(cli, env, cwd, monkeypatch):
    monkeypatch.setattr(doctor, "_PROBE_TIMEOUT_S", 1)
    env["FAKE_SLEEP"] = "5"
    found = mods(run(env, cwd, mods=True, executable=cli))
    assert len(found) == 1 and not found[0].ok and "timed out after 1s" in found[0].detail
    assert found[0].fix


def test_a_missing_cli_skips_the_check_and_fails(tmp_path, env, cwd):
    found = mods(run(env, cwd, mods=True, executable=str(tmp_path / "nope")))
    assert len(found) == 1 and not found[0].ok and found[0].detail == "skipped: claude cli"


def test_a_hostile_plugin_name_and_path_print_safely(cli, env, cwd):
    path = "/s/\x1b[2Jevil"
    env["FAKE_LIST"] = json.dumps([entry("\x1b]0;x\x07@skills-dir", path)])
    env["FAKE_REPORTS"] = json.dumps({path: report("tool.call\x1b[31m")})
    text = render_doctor(run(env, cwd, mods=True, executable=cli))
    assert "\x1b" not in text and "\x07" not in text


def test_the_cli_flag_reaches_the_check_and_sets_the_exit_code(cli, env, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    env["FAKE_LIST"] = json.dumps([entry("gatemod@skills-dir", "/s/g")])
    env["FAKE_REPORTS"] = json.dumps({"/s/g": report("tool.call")})
    configure(env, cli)
    environ = {"BOSS_CLAUDE_BIN": cli, "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    said: list[str] = []
    argv = ["doctor", "--mods", "--dir", str(project)]
    code = antstreet_cli.main(argv, say=said.append, environ=environ)
    assert "mod gatemod@skills-dir" in "\n".join(said)
    assert code == antstreet_cli.EXIT_FAILED
