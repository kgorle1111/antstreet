"""The Claude Code plugin front door: its manifests load, every CLI call it makes exists, its grants
stay read-only, and its hooks behave (silent when there is nothing to say, never install, never
block)."""

import json
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from boss import cli

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin"
HOOKS = ROOT / "hooks"
PROMPTS = sorted((ROOT / "commands").glob("*.md")) + [ROOT / "skills" / "antstreet" / "SKILL.md"]
CALL = re.compile(r"uvx antstreet ([a-z]+)((?: --?[a-z-]+)*)")
# What the plugin may run without asking: reading a run and the free machine check, nothing that
# spends money or needs the investor's own answer at a terminal.
READ_ONLY = {"status", "report", "doctor"}
UV_FIX = "curl -LsSf https://astral.sh/uv/install.sh | sh"


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path.name}: no frontmatter"
    head = text[4 : text.index("\n---\n", 4)]
    return dict(line.split(": ", 1) for line in head.splitlines())


def subcommands() -> dict[str, set[str]]:
    """Each `boss` command and the option strings it accepts."""
    choices = cli._parser()._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    return {name: set(p._option_string_actions) for name, p in choices.items()}


def test_the_plugin_manifest_names_the_plugin_and_its_version_matches_the_package():
    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    assert manifest["name"] == "antstreet"
    assert manifest["author"]["name"] and manifest["description"]
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{manifest["version"]}"' in pyproject


def test_the_repository_is_its_own_marketplace_listing_the_plugin_at_its_root():
    market = json.loads((PLUGIN / "marketplace.json").read_text())
    assert market["name"] == "antstreet" and market["owner"]["name"]
    [entry] = market["plugins"]
    assert entry == entry | {"name": "antstreet", "source": "./"}
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", market["name"])  # the install id's rules


@pytest.mark.parametrize("path", PROMPTS, ids=lambda p: p.name)
def test_each_prompt_has_a_description_and_calls_only_real_cli_commands(path):
    meta = frontmatter(path)
    assert meta["description"]
    known = subcommands()
    calls = CALL.findall(path.read_text())
    assert calls, f"{path.name} calls no antstreet command"
    for command, options in calls:
        assert command in known, f"{path.name}: `antstreet {command}` is not a command"
        for option in options.split():
            assert option in known[command], f"{path.name}: `{command} {option}` does not exist"


def test_the_skill_is_named():
    assert frontmatter(ROOT / "skills" / "antstreet" / "SKILL.md")["name"] == "antstreet"


@pytest.mark.parametrize("path", PROMPTS, ids=lambda p: p.name)
def test_no_prompt_grants_a_command_that_spends_or_needs_the_investor(path):
    grants = re.findall(r"Bash\(([^)]*)\)", frontmatter(path).get("allowed-tools", ""))
    assert grants
    for grant in grants:
        command = re.fullmatch(r"uvx antstreet ([a-z]+)(?: \*)?", grant)
        assert command, f"{path.name}: {grant!r} is not a single antstreet command"
        assert command[1] in READ_ONLY, f"{path.name}: {grant!r} is not read-only"
        assert grant != "uvx antstreet doctor *", f"{path.name}: it would allow `doctor --live`"


def test_the_cli_calls_checker_can_fail():
    assert ("fnud", "") in CALL.findall("run `uvx antstreet fnud`")
    assert "fnud" not in subcommands()
    assert "--live" not in subcommands()["status"]


def test_hooks_json_points_at_executable_scripts_that_exist():
    config = json.loads((HOOKS / "hooks.json").read_text())
    assert set(config["hooks"]) == {"SessionStart", "Stop"}
    for groups in config["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                assert hook["type"] == "command" and 0 < hook["timeout"] <= 60
                script = re.fullmatch(r'"\$\{CLAUDE_PLUGIN_ROOT\}"/(\S+)', hook["command"])
                assert script, hook["command"]
                target = ROOT / script[1]
                assert target.is_file() and target.stat().st_mode & stat.S_IXUSR, target


def _run(script: str, path: str, project: Path) -> subprocess.CompletedProcess[str]:
    env = {"PATH": path, "CLAUDE_PROJECT_DIR": str(project), "HOME": str(project)}
    return subprocess.run(
        [str(HOOKS / script)], env=env, capture_output=True, text=True, timeout=30, check=False
    )


def _bin(tmp_path: Path, uvx: str | None) -> str:
    """A PATH holding the basic tools the scripts use, plus a fake `uvx` when given its body."""
    folder = tmp_path / "bin"
    folder.mkdir()
    for tool in ("ls", "touch"):
        found = shutil.which(tool)
        assert found
        (folder / tool).symlink_to(found)
    if uvx is not None:
        fake = folder / "uvx"
        fake.write_text(f"#!/bin/sh\n{uvx}\n")
        fake.chmod(0o755)
    return str(folder)


def test_session_start_says_the_one_install_command_when_uvx_is_missing(tmp_path):
    done = _run("check-uv.sh", _bin(tmp_path, None), tmp_path)
    assert done.returncode == 0
    message = json.loads(done.stdout)
    assert UV_FIX in message["systemMessage"]
    assert UV_FIX in message["hookSpecificOutput"]["additionalContext"]


def test_session_start_is_silent_when_uvx_is_there(tmp_path):
    done = _run("check-uv.sh", _bin(tmp_path, "exit 0"), tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")


def test_stop_is_silent_and_runs_nothing_in_a_project_without_runs(tmp_path):
    marker = tmp_path / "ran"
    path = _bin(tmp_path, f"touch {marker}")
    for _ in range(2):  # no `.boss/runs`, then the folder with no run in it
        done = _run("ledger-check.sh", path, tmp_path)
        assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
        (tmp_path / ".boss" / "runs").mkdir(parents=True, exist_ok=True)
    assert not marker.exists()


def test_stop_reads_the_latest_run_with_status_and_reports_a_failure_without_blocking(tmp_path):
    (tmp_path / ".boss" / "runs" / "r1").mkdir(parents=True)
    log = tmp_path / "args"
    ok = _run("ledger-check.sh", _bin(tmp_path, f'echo "$@" > {log}'), tmp_path)
    assert (ok.returncode, ok.stderr) == (0, "")
    assert log.read_text().split() == ["antstreet", "status", "--dir", str(tmp_path)]
    (tmp_path / "bin").rename(tmp_path / "old")
    bad = _run("ledger-check.sh", _bin(tmp_path, "echo 'Stopped: signature'; exit 1"), tmp_path)
    assert bad.returncode == 1  # a non-blocking error; 2 would hand it to the agent being checked
    assert "did not verify" in bad.stderr and "Stopped: signature" in bad.stderr


MOD = HOOKS / "approve-pane.tsx"
APPROVE_CALL = re.compile(r"^.*\bapprove\(\$.*$", re.M)


def test_the_approve_pane_mod_is_the_one_hooks_module_and_its_contract_is_named():
    assert json.loads((HOOKS / "hooks.json").read_text())["modules"] == ["./approve-pane.tsx"]
    manifest = json.loads((PLUGIN / "plugin.json").read_text())
    assert (ROOT / manifest["types"]).is_file() and MOD.is_file()


def test_the_mod_approves_only_from_the_approve_buttons_press():
    """The mods API has no method that presses a Button, so a press is a person. This holds the
    source to that: one `--sheet` call, inside `approve`, which only an onPress calls; and nothing
    the model could reach (a tool, a prompt, a hotkey or a keybinding action on any Button)."""
    source = MOD.read_text()
    body = source[source.index("async function approve(") :]
    body = body[: body.index("\n}\n")]
    assert source.count("'--sheet'") == 1 and "'--sheet'" in body
    calls = APPROVE_CALL.findall(source.replace(body, ""))
    assert len(calls) == 1 and "onPress=" in calls[0], calls
    for banned in (
        "hotkey",
        "action=",
        "$.tool",
        "$.prompt",
        "$.agent",
        "$.model",
        "tool.call",
        "tool.check",
        "prompt.submit",
        "asUser",
        "ui.press",
    ):
        assert banned not in source, banned


def test_the_mod_checker_can_fail():
    body = "async function approve($) {\n  run(['approve', r, '--sheet', v])\n}\n"
    leaked = body + "on('session.start', $ => approve($, cli))\n"
    found = APPROVE_CALL.findall(leaked.replace(body, ""))
    assert found and "onPress=" not in found[0]
