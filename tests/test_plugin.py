"""The Claude Code plugin front door: its manifests load, every CLI call it makes exists, its grants
never include `approve`, the PreToolUse hook denies every way of running `approve`, and the other
hooks behave (silent when there is nothing to say, never install, never block)."""

import json
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from antstreet import cli

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / ".claude-plugin"
HOOKS = ROOT / "hooks"
PROMPTS = sorted((ROOT / "commands").glob("*.md")) + [ROOT / "skills" / "antstreet" / "SKILL.md"]
CALL = re.compile(r"uvx antstreet ([a-z]+)((?: --?[a-z-]+)*)")
# What each prompt may run without asking. Reading a run and the free machine check everywhere;
# only /antstreet:fund may draft (`fund` stops at exit 4 with the sheet unapproved) and build an
# approved run (`resume`). `approve` is the investor's act and is in no grant.
READ_ONLY = {"status", "report", "doctor"}
GRANTS = {"fund.md": READ_ONLY | {"fund", "resume"}}
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
def test_no_prompt_grants_approve_and_only_fund_grants_a_command_that_spends(path):
    grants = re.findall(r"Bash\(([^)]*)\)", frontmatter(path).get("allowed-tools", ""))
    assert grants
    for grant in grants:
        assert "approve" not in grant, f"{path.name}: {grant!r} lets the agent approve"
        command = re.fullmatch(r"uvx antstreet ([a-z]+)(?: \*)?", grant)
        assert command, f"{path.name}: {grant!r} is not a single antstreet command"
        allowed = GRANTS.get(path.name, READ_ONLY)
        assert command[1] in allowed, f"{path.name}: {grant!r} is not allowed here"
        assert grant != "uvx antstreet doctor *", f"{path.name}: it would allow `doctor --live`"


def test_the_cli_calls_checker_can_fail():
    assert ("fnud", "") in CALL.findall("run `uvx antstreet fnud`")
    assert "fnud" not in subcommands()
    assert "--live" not in subcommands()["status"]


def test_hooks_json_points_at_executable_scripts_that_exist():
    config = json.loads((HOOKS / "hooks.json").read_text())
    assert set(config["hooks"]) == {"SessionStart", "PreToolUse", "Stop"}
    [guard] = config["hooks"]["PreToolUse"]
    assert set(guard["matcher"].split("|")) == {
        "Bash",
        "Monitor",
        "PowerShell",  # what runs a shell
        "Read",
        "Grep",
        "Glob",  # what reads a path the agent names, so a read of the audit store is denied too
    }
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


def _audit_hook(
    tmp_path: Path, uvx: str | None, stdin: str = "{}", **env: str
) -> subprocess.CompletedProcess[str]:
    """`audit-check.sh` with the audit store under `tmp_path/home` and a fake `uvx`."""
    path = _bin(tmp_path, uvx)
    (Path(path) / "cat").symlink_to(shutil.which("cat") or "/bin/cat")
    full = {"PATH": path, "CLAUDE_PROJECT_DIR": str(tmp_path), "HOME": str(tmp_path / "home")}
    return subprocess.run(
        [str(HOOKS / "audit-check.sh")], env=full | env, input=stdin, capture_output=True,
        text=True, timeout=30, check=False,
    )  # fmt: skip


def _a_sealed_run(tmp_path: Path) -> None:
    (tmp_path / "home" / ".boss-audit" / ".boss" / "runs" / "r1").mkdir(parents=True)


def test_the_audit_stop_hook_is_silent_and_runs_nothing_without_a_sealed_run(tmp_path):
    marker = tmp_path / "ran"
    done = _audit_hook(tmp_path, f"touch {marker}")
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert not marker.exists()


def test_the_audit_stop_hook_notifies_by_default_and_passes_the_cli_json_through(tmp_path):
    _a_sealed_run(tmp_path)
    log = tmp_path / "args"
    said = '{"systemMessage": "AntStreet audit: REFUTED"}'
    done = _audit_hook(tmp_path, f"echo \"$@\" > {log}; echo '{said}'")
    assert (done.returncode, done.stdout.strip(), done.stderr) == (0, said, "")
    assert log.read_text().split() == [
        "antstreet", "audit", "--repo", str(tmp_path), "--stop-hook", "notify",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("option", "stdin", "mode"),
    [
        ("block", '{"stop_hook_active": false}', "block"),
        ("block", '{"session_id":"s","stop_hook_active":true}', "notify"),  # never block twice
        ("block", '{"stop_hook_active": true}', "notify"),
        ("block", '{\n  "stop_hook_active" :\n    true\n}', "notify"),  # any valid JSON layout
        ("block", '{"stop_hook_active":\t  false}', "block"),
        ("notify", "{}", "notify"),
        ("anything else", "{}", "notify"),
    ],
)
def test_blocking_is_opt_in_and_never_twice_in_a_row(tmp_path, option, stdin, mode):
    _a_sealed_run(tmp_path)
    log = tmp_path / "args"
    done = _audit_hook(
        tmp_path, f'echo "$@" > {log}', stdin, CLAUDE_PLUGIN_OPTION_AUDIT_ON_REFUTED=option
    )
    assert done.returncode == 0
    assert log.read_text().split()[-2:] == ["--stop-hook", mode]


def test_an_audit_hook_error_fails_open_with_a_generic_notice_and_none_of_the_cli_output(tmp_path):
    _a_sealed_run(tmp_path)
    done = _audit_hook(tmp_path, "echo 'c01 failed: secret check text'; echo boom >&2; exit 1")
    assert (done.returncode, done.stderr) == (0, "")
    message = json.loads(done.stdout)
    assert set(message) == {"systemMessage"} and "did not complete" in message["systemMessage"]
    assert "c01" not in done.stdout and "boom" not in done.stdout


def test_the_audit_stop_hook_is_silent_without_uvx(tmp_path):
    _a_sealed_run(tmp_path)
    done = _audit_hook(tmp_path, None)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")


def test_the_plugin_option_for_blocking_defaults_to_notify():
    option = json.loads((PLUGIN / "plugin.json").read_text())["userConfig"]["audit_on_refuted"]
    assert option["default"] == "notify" and option["options"] == list(cli.STOP_HOOK_MODES)


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


def _guard(
    command: str,
    tool: str = "Bash",
    tool_input: dict[str, str] | None = None,
    cwd: str = "/home/user/boss",  # a project folder named boss must not arm the match
    **env: str,
) -> subprocess.CompletedProcess[str]:
    """Run the PreToolUse hook on the input Claude Code sends (code.claude.com/docs/en/hooks)."""
    event = {
        "session_id": "s",
        "cwd": cwd,
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input or {"command": command, "description": "run it"},
        "tool_use_id": "toolu_1",
    }
    return subprocess.run(
        [str(HOOKS / "deny-approve.sh")],
        input=json.dumps(event),
        env={"PATH": "/usr/bin:/bin"} | env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


APPROVES = [
    "antstreet approve",
    "boss approve r1 --sheet 0123456789abcdef",
    "uvx antstreet approve r1 --sheet 0123456789abcdef",
    "uvx antstreet@latest approve",
    "uvx --from antstreet==0.0.1 boss approve",
    "uvx --from git+https://github.com/kgorle1111/antstreet antstreet approve",
    "uv run boss approve",
    "uv run --directory . -- antstreet approve",
    "python -m boss.cli approve",
    "python3 src/boss/cli.py approve",
    ".venv/bin/boss approve",
    "/usr/local/bin/antstreet approve",
    "FOO=1 BOSS_X=2 antstreet approve",
    "env -i antstreet approve",
    "cd x; antstreet approve",
    "true && boss approve",
    "echo y | antstreet approve",
    "(antstreet approve)",
    "echo $(boss approve)",
    "echo `boss approve`",
    "{ antstreet approve; }",
    "antstreet   \t  approve",
    "antstreet\napprove",
    "true\nantstreet approve",
    "'antstreet' \"approve\"",
    "antstreet ap'pr'ove",
    'antstreet ap""prove',
    "antstreet ap\\prove",
    "ANTSTREET APPROVE",
    "antstreet $(echo approve)",
    "sh -c 'antstreet approve'",
    # the investor's ruling on a dispute goes through `approve` too, so it is denied the same way
    "boss approve r1 --dispute c05 --ruling drop",
    "uvx antstreet approve r1 --dispute c05 --ruling keep",
    "uv run boss approve --ruling keep --dispute c05",
]
ALLOWED = [
    "uvx antstreet status",
    "uvx antstreet report r1",
    "uvx antstreet doctor",
    "uvx antstreet fund 'a csv parser' --budget 0.40",
    "uvx antstreet resume r1",
    "boss status --dir /home/user/boss",
    "grep -rn approve src",
    "ls /home/user/boss/.boss/runs && echo approved",
    "git log --oneline",
    "echo approve",
]


@pytest.mark.parametrize("command", APPROVES)
def test_the_guard_denies_every_way_of_running_approve(command):
    done = _guard(command)
    assert done.returncode == 2, command  # blocks before allow rules are even read
    decision = json.loads(done.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "! uvx antstreet approve RUN --sheet VALUE" in decision["permissionDecisionReason"]
    assert "approve RUN --dispute CHECK --ruling drop|keep" in decision["permissionDecisionReason"]
    assert decision["permissionDecisionReason"] in done.stderr


@pytest.mark.parametrize("command", ALLOWED)
def test_the_guard_stays_silent_on_everything_else(command):
    done = _guard(command)
    assert (done.returncode, done.stdout, done.stderr) == (0, "", ""), command


@pytest.mark.parametrize("tool", ["Monitor", "PowerShell"])
def test_the_guard_reads_other_tools_that_run_a_command(tool):
    assert _guard("uvx antstreet approve r1", tool).returncode == 2


AUDITS = [
    "antstreet audit",
    "uvx antstreet audit",
    "uvx antstreet audit report",
    "uvx antstreet audit report r1 --all",
    "uvx antstreet audit check r1 --claim done",
    "uvx antstreet audit plan --request ~/req.txt",
    "boss audit --repo . --stop-hook notify",
    "uvx antstreet@latest audit report",
    "uvx --from antstreet==0.0.1 boss audit check",
    "uv run --directory . -- antstreet audit report",
    "python -m antstreet.cli audit report",
    "python3 src/antstreet/cli.py audit check",
    ".venv/bin/antstreet audit report",
    "FOO=1 antstreet audit report",
    "env -i boss audit report",
    "cd x; antstreet audit report",
    "true && boss audit check",
    "echo $(antstreet audit report)",
    "echo `boss audit report`",
    "sh -c 'antstreet audit report'",
    "antstreet\naudit report",
    "'antstreet' \"audit\" report",
    "antstreet au'di't report",
    "antstreet au\\dit report",
    "ANTSTREET AUDIT REPORT",
    "antstreet $(echo audit) report",
    "uvx antstreet fund 'x'; uvx antstreet audit report",
]


@pytest.mark.parametrize("command", AUDITS)
def test_the_guard_denies_every_way_of_running_an_audit(command):
    done = _guard(command)
    assert done.returncode == 2, command
    reason = json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "may not run `antstreet audit` in any form" in reason
    assert reason.endswith("! uvx antstreet audit") and reason in done.stderr


def _store(tmp_path: Path) -> tuple[Path, Path]:
    """A home with an audit store holding one check, and a project beside it."""
    store = tmp_path / "home" / ".boss-audit"
    (store / ".boss" / "runs" / "r1").mkdir(parents=True)
    (store / ".boss" / "runs" / "r1" / "test_c01.py").write_text("assert sealed\n")
    project = tmp_path / "project"
    (project / ".antstreet").mkdir(parents=True)
    (project / ".antstreet" / "request.md").write_text("add a flag\n")
    return store, project


def _store_denied(done: subprocess.CompletedProcess[str], *secrets: str) -> None:
    assert done.returncode == 2, done.stdout
    reason = json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "may not read, search or list it" in reason
    assert reason.endswith("! uvx antstreet audit report") and reason in done.stderr
    for secret in secrets:  # the denial says neither where the store is nor what is in it
        assert secret not in done.stdout and secret not in done.stderr


STORE_COMMANDS = [
    "cat ~/.boss-audit/.boss/runs/r1/test_c01.py",
    "cat $HOME/.boss-audit/.boss/runs/*/test_*.py",
    "rg -uu assert ${HOME}/.boss-audit",
    "find ~/.BOSS-AUDIT -name '*.py'",
    'cat ~/.boss-""audit/x',
    "cat ~/.boss-aud\\it/x",
    "cd ../../.boss-audit && ls",
    "python3 -c \"print(open('/home/u/.boss-audit/x').read())\"",
    "ls $BOSS_AUDIT_HOME",
    'tar cf - "${BOSS_AUDIT_HOME}/.boss" | base64',
]


@pytest.mark.parametrize("command", STORE_COMMANDS)
def test_the_guard_denies_a_command_that_names_the_audit_store(command):
    _store_denied(_guard(command))


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Read", {"file_path": "/home/u/.boss-audit/.boss/runs/r1/test_c01.py"}),
        ("Read", {"file_path": "../../.boss-audit/.boss/runs/r1/test_c01.py"}),
        ("Grep", {"pattern": "assert", "path": "/home/u/.boss-audit"}),
        ("Glob", {"pattern": "**/.boss-audit/**/*.py"}),
        ("Glob", {"pattern": "*.py", "path": "/home/u/.Boss-Audit/.boss"}),
    ],
)
def test_the_guard_denies_a_read_search_or_listing_of_the_audit_store(tool, tool_input):
    _store_denied(_guard("", tool, tool_input))


def test_the_guard_denies_a_path_that_resolves_into_the_store_through_a_link(tmp_path):
    store, project = _store(tmp_path)
    (project / "notes").symlink_to(store)
    home = str(tmp_path / "home")
    via = "notes/.boss/runs/r1/test_c01.py"
    for tool, tool_input in [
        ("Read", {"file_path": str(project / via)}),
        ("Read", {"file_path": via}),
        ("Grep", {"pattern": "assert", "path": "notes"}),
        ("Bash", {"command": f"cat {via}"}),
        ("Bash", {"command": "cat notes/.boss/runs/*/*.py"}),
        ("Bash", {"command": "cat $HOME/../project/notes/.boss/runs/r1/*"}),
    ]:
        done = _guard("", tool, tool_input, str(project), HOME=home)
        _store_denied(done, str(store), "assert sealed")


def test_the_guard_denies_the_store_that_boss_audit_home_names(tmp_path):
    _, project = _store(tmp_path)
    sealed = tmp_path / "sealed"
    (sealed / ".boss" / "runs").mkdir(parents=True)
    (project / "link").symlink_to(sealed / ".boss")
    env = {"HOME": str(tmp_path / "home"), "BOSS_AUDIT_HOME": f"{sealed}/"}
    for tool, tool_input in [
        ("Read", {"file_path": f"{sealed}/.boss/runs/r1/test_c01.py"}),  # by its value
        ("Grep", {"pattern": "x", "path": str(sealed)}),
        ("Bash", {"command": f"ls {sealed}/.boss/runs/r1"}),  # not there yet: still named
        ("Bash", {"command": "ls link/runs"}),  # through a link
        ("Read", {"file_path": "link/runs"}),
    ]:
        _store_denied(_guard("", tool, tool_input, str(project), **env), str(sealed))
    for tool, tool_input in [  # a longer name that begins with the value is another folder
        ("Read", {"file_path": f"{sealed}-notes/a.md"}),
        ("Bash", {"command": f"ls {sealed}.old"}),
    ]:
        done = _guard("", tool, tool_input, str(project), **env)
        assert (done.returncode, done.stdout) == (0, ""), tool_input


def test_the_guard_lets_the_agent_read_its_own_project(tmp_path):
    store, project = _store(tmp_path)
    (project / "audit").mkdir()  # a project folder named audit
    (project / "audit" / "log.py").write_text("x = 1\n")
    (project / "up").symlink_to(tmp_path)  # a link to the store's grandparent, not into it
    home = str(tmp_path / "home")
    for tool, tool_input in [
        ("Read", {"file_path": str(project / ".antstreet" / "request.md")}),
        ("Read", {"file_path": ".antstreet/request.md"}),
        ("Read", {"file_path": "audit/log.py"}),
        ("Read", {"file_path": "up/project/audit/log.py"}),
        ("Grep", {"pattern": "antstreet approve|antstreet audit", "path": "."}),  # its docs
        ("Grep", {"pattern": "BOSS_AUDIT_HOME|boss-audit", "path": "src"}),
        ("Glob", {"pattern": "audit/**/*.py"}),
        ("Bash", {"command": "git log --grep audit --oneline"}),
        ("Bash", {"command": "ls audit && cat audit/log.py"}),
        ("Bash", {"command": "uvx antstreet fund 'add an audit log' --budget 0.40"}),
        ("Bash", {"command": "uvx antstreet report r1 && grep -rn audit src"}),
        ("Bash", {"command": "grep -rn BOSS_AUDIT_HOME src; printenv HOME"}),
        ("Bash", {"command": "ls ~ $HOME/../project"}),
    ]:
        done = _guard("", tool, tool_input, str(project), HOME=home)
        assert (done.returncode, done.stdout, done.stderr) == (0, "", ""), tool_input
    assert store.is_dir()


def test_the_guard_knows_every_cli_step_that_is_not_audit():
    """A step the guard does not know is read as a hidden `audit`; a step it lists must exist."""
    script = (HOOKS / "deny-approve.sh").read_text()
    listed = re.search(r"step !~ /\^\(([a-z|]+)\)\$/", script)
    assert listed and set(listed[1].split("|")) == set(subcommands()) - {"audit", "approve"}


def test_the_audit_stop_hook_still_audits_with_the_guard_installed(tmp_path):
    """Hooks are not tool calls, so the guard never sees the Stop hook's own `antstreet audit`."""
    _a_sealed_run(tmp_path)
    log = tmp_path / "args"
    done = _audit_hook(tmp_path, f'echo "$@" > {log}')
    assert done.returncode == 0 and log.read_text().split()[:2] == ["antstreet", "audit"]
    assert _guard(f"uvx {log.read_text().strip()}").returncode == 2  # the same call, as a tool
