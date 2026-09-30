import copy
from pathlib import Path

import pytest

from boss.stream import StreamReader
from boss.worker import (
    SCHEMA_TOOL,
    WORKER_TOOLS,
    IsolationError,
    isolation_violations,
    require_isolation,
)

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> StreamReader:
    reader = StreamReader()
    for line in (FIXTURES / name).read_text().splitlines():
        reader.feed(line)
    return reader


def test_recorded_isolated_worker_passes():
    # Probe P4 ran with exactly Read/Write/Edit and no schema, so StructuredOutput is not expected.
    reader = read("stream_budget_capped_2.1.285.jsonl")
    assert (
        isolation_violations(
            reader.init, hook_events=reader.hook_events, expected_tools=WORKER_TOOLS
        )
        == []
    )


def test_default_expectation_includes_the_schema_tool():
    reader = read("stream_budget_capped_2.1.285.jsonl")
    [problem] = isolation_violations(reader.init, hook_events=reader.hook_events)
    assert problem == f"tools differ: extra=[] missing=['{SCHEMA_TOOL}']"


def test_recorded_unisolated_run_is_refused_for_every_reason():
    # Probe P1: plain -p on a login that loaded a session-start hook and the default tool set.
    reader = read("stream_auth_expired_2.1.285.jsonl")
    problems = isolation_violations(reader.init, hook_events=reader.hook_events)
    assert any(p.startswith("tools differ") for p in problems)
    assert "permission mode is 'default', expected 'dontAsk'" in problems
    assert "2 hook event(s) ran" in problems
    with pytest.raises(IsolationError, match="hook event"):
        require_isolation(reader.init, hook_events=reader.hook_events)


def test_a_shell_tool_is_refused():
    reader = read("stream_permission_denials_2.1.285.jsonl")
    [problem] = isolation_violations(reader.init, hook_events=0, expected_tools=WORKER_TOOLS)
    assert problem == "tools differ: extra=['Bash'] missing=[]"


def isolated_init() -> dict:
    init = copy.deepcopy(read("stream_budget_capped_2.1.285.jsonl").init)
    init["tools"] = [*WORKER_TOOLS, SCHEMA_TOOL]
    return init


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"mcp_servers": [{"name": "Airtable", "status": "connected"}]}, "MCP servers present"),
        ({"mcp_servers": None}, "MCP servers present"),
        ({"claude_code_version": "2.1.178"}, "below 2.1.277"),
        ({"claude_code_version": None}, "below 2.1.277"),
        ({"tools": None}, "init has no tools list"),
    ],
    ids=["connector", "no-mcp-field", "old-cli", "no-version", "no-tools"],
)
def test_each_violation_is_named(change, expected):
    init = isolated_init() | change
    [problem] = isolation_violations(init, hook_events=0)
    assert expected in problem


def test_derived_isolated_init_passes_with_the_default_expectation():
    assert isolation_violations(isolated_init(), hook_events=0) == []
    require_isolation(isolated_init(), hook_events=0)


def test_missing_init_is_refused():
    with pytest.raises(IsolationError, match="no system/init"):
        require_isolation(None, hook_events=0)
