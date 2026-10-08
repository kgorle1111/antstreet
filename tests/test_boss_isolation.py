"""A boss or role call that did not start isolated fails closed: no output used, spend booked.

The fake executables replay lines of CLI output; each violation is one change to the init event
(or a hook event) that `worker.isolation_violations` must refuse, exactly as for a worker slice.
"""

import json
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT, BOSS_INIT_LINE

from antstreet.boss import (
    BOSS_TOOLS,
    BossError,
    BossIsolationError,
    build_boss_command,
    draft_term_sheet,
)
from antstreet.errors import Outcome
from antstreet.roles.base import RoleError, RoleSpec, call_role
from antstreet.worker import SCHEMA_TOOL

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "json_boss_schema_call_2.1.285.json").read_text()
)
COST = 3634  # micro-dollars in the recorded call
CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
RESULT = RECORDED | {"structured_output": DRAFT}
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}
ROLE_RESULT = RECORDED | {"structured_output": {"answer": "x"}}
HOOK = {"type": "system", "subtype": "hook_started", "hook_name": "late"}
FAKE = f"""#!{sys.executable}
import os, sys
sys.stdout.write(os.environ["FAKE_LINES"])
"""


@pytest.fixture
def cli(tmp_path):
    path = tmp_path / "fake-claude"
    path.write_text(FAKE)
    path.chmod(0o755)

    def env(lines):
        text = "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines)
        return {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "FAKE_LINES": text + "\n"}

    def draft(lines):
        return draft_term_sheet(
            "Reverse a string.",
            500_000,
            tmp_path / "checks",
            env=env(lines),
            executable=str(path),
        )

    def role(lines):
        spec = RoleSpec("tester", "engineering", "boss", "writes", "a gate", "term_sheet_v1.md")
        return call_role(
            spec, "Idea:\nx", SCHEMA, env=env(lines), model="haiku", executable=str(path)
        )

    draft.role, draft.checks = role, tmp_path / "checks"
    return draft


VIOLATIONS = {
    "a shell tool": (BOSS_INIT | {"tools": [SCHEMA_TOOL, "Bash"]}, "extra=['Bash']"),
    "the default tool set": (
        BOSS_INIT | {"tools": ["Read", "Edit", "Write", SCHEMA_TOOL]},
        "extra=",
    ),
    "a web tool": (BOSS_INIT | {"tools": [SCHEMA_TOOL, "WebFetch"]}, "extra=['WebFetch']"),
    "no schema tool": (BOSS_INIT | {"tools": []}, f"missing=['{SCHEMA_TOOL}']"),
    "no tools field": (BOSS_INIT | {"tools": None}, "init has no tools list"),
    "an MCP server": (
        BOSS_INIT | {"mcp_servers": [{"name": "Airtable", "status": "connected"}]},
        "MCP servers present",
    ),
    "no MCP field": (BOSS_INIT | {"mcp_servers": None}, "MCP servers present"),
    "default permission mode": (BOSS_INIT | {"permissionMode": "default"}, "permission mode is"),
    "bypass permissions": (
        BOSS_INIT | {"permissionMode": "bypassPermissions"},
        "permission mode is 'bypassPermissions'",
    ),
    "an old CLI": (BOSS_INIT | {"claude_code_version": "2.1.178"}, "below 2.1.277"),
}


def test_the_expected_tool_set_is_only_the_schema_tool():
    assert BOSS_TOOLS == (SCHEMA_TOOL,)


def test_an_isolated_call_is_accepted(cli):
    assert cli([BOSS_INIT, RESULT]).sheet.checks[0].description == "reverses a word"
    assert cli.role([BOSS_INIT, ROLE_RESULT]).data == {"answer": "x"}


@pytest.mark.parametrize(("init", "named"), VIOLATIONS.values(), ids=VIOLATIONS.keys())
def test_a_draft_whose_init_shows_a_violation_is_refused_and_its_spend_booked(cli, init, named):
    with pytest.raises(BossIsolationError, match="isolation failure") as caught:
        cli([init, RESULT])
    assert named in str(caught.value)
    assert caught.value.usage.cost_micros == COST
    assert caught.value.outcome is Outcome.CRASHED
    assert not cli.checks.exists() or not list(cli.checks.iterdir())  # no output was used


@pytest.mark.parametrize(("init", "named"), VIOLATIONS.values(), ids=VIOLATIONS.keys())
def test_a_role_whose_init_shows_a_violation_is_refused_and_its_spend_booked(cli, init, named):
    with pytest.raises(RoleError, match="isolation failure") as caught:
        cli.role([init, ROLE_RESULT])
    assert named in str(caught.value)
    assert caught.value.usage.cost_micros == COST
    assert caught.value.outcome is Outcome.CRASHED


def test_a_completed_call_with_no_init_event_is_refused(cli):
    with pytest.raises(BossIsolationError, match="no system/init event arrived") as caught:
        cli([RESULT])
    assert caught.value.usage.cost_micros == COST


@pytest.mark.parametrize("position", ["before init", "between", "after the result"])
def test_a_hook_event_anywhere_in_the_stream_is_refused(cli, position):
    lines = {
        "before init": [HOOK, BOSS_INIT, RESULT],
        "between": [BOSS_INIT, HOOK, RESULT],
        "after the result": [BOSS_INIT, RESULT, HOOK],
    }[position]
    with pytest.raises(BossIsolationError, match="1 hook event"):
        cli(lines)


def test_a_violating_init_is_reported_even_when_the_call_failed(cli):
    failed = RESULT | {"is_error": True, "api_error_status": 500, "terminal_reason": "api_error"}
    with pytest.raises(BossIsolationError, match="extra=\\['Bash'\\]"):
        cli([BOSS_INIT | {"tools": [SCHEMA_TOOL, "Bash"]}, failed])


def test_a_hook_event_fails_a_call_even_if_it_died_before_init(cli):
    failed = RESULT | {"is_error": True, "api_error_status": 500, "terminal_reason": "api_error"}
    with pytest.raises(BossIsolationError, match="no system/init event arrived"):
        cli([HOOK, failed])


def test_a_failed_call_that_never_reached_init_keeps_its_own_outcome(cli):
    failed = RESULT | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"}
    with pytest.raises(BossError) as caught:
        cli([failed])
    assert not isinstance(caught.value, BossIsolationError)
    assert caught.value.outcome is Outcome.LOGIN


def test_a_line_separator_inside_the_answer_does_not_split_the_event(cli):
    # json.dumps(ensure_ascii=False) leaves U+2028 raw; str.splitlines() would cut the event there.
    brief = "Create rev.py with reverse(s)."
    draft = DRAFT | {"tasks": [{"id": "t1", "brief": brief, "paths": ["rev.py"]}]}
    line = json.dumps(RESULT | {"structured_output": draft}, ensure_ascii=False)
    assert cli([BOSS_INIT_LINE, line]).sheet.tasks[0].brief == brief


def test_the_command_asks_for_the_events_the_check_needs():
    argv = build_boss_command(
        prompt="p", system_prompt="s", schema={}, model="haiku", cap_micros=1000, api_key=False
    )
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv  # the worker command passes it with stream-json too
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"


def test_the_recorded_no_tool_call_passes_the_check_it_is_held_to():
    """The real init of a boss call, recorded with the exact argv, is what the check expects."""
    from boss_init import BOSS_INIT

    from antstreet.boss import BOSS_TOOLS
    from antstreet.worker import isolation_violations

    assert BOSS_INIT["tools"] == ["StructuredOutput"] and BOSS_INIT["mcp_servers"] == []
    assert BOSS_INIT["permissionMode"] == "dontAsk"
    assert isolation_violations(BOSS_INIT, hook_events=0, expected_tools=BOSS_TOOLS) == []
