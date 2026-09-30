import json
from uuid import UUID

import pytest

from boss.ledger import Billing
from boss.worker import SliceSpec, billing_mode, build_command, worker_env

SID = UUID("12345678-1234-5678-1234-567812345678")
SCHEMA = (
    '{"type":"object","properties":{"status":{"type":"string",'
    '"enum":["done","continuing","blocked"]},"reason":{"type":"string"}},'
    '"required":["status","reason"]}'
)


def spec(**overrides) -> SliceSpec:
    base = {
        "session_id": SID,
        "resume": False,
        "prompt": "Implement the task in BRIEF.md.",
        "model": "haiku",
        "cap_cents": 30,
    }
    return SliceSpec(**(base | overrides))


def test_first_slice_with_subscription_login():
    assert build_command(spec(), api_key=False) == [
        "claude", "--print", "--output-format", "stream-json", "--verbose", "--safe-mode",
        "--model", "haiku",
        "--tools", "Read,Write,Edit",
        "--allowedTools", "Read(./**) Write(./**) Edit(./**)",
        "--permission-mode", "dontAsk",
        "--max-budget-usd", "0.30",
        "--json-schema", SCHEMA,
        "--session-id", str(SID),
        "Implement the task in BRIEF.md.",
    ]  # fmt: skip


def test_resumed_slice_with_api_key_and_role_prompt():
    argv = build_command(
        spec(resume=True, cap_cents=125, append_system_prompt="You are a builder."), api_key=True
    )
    assert argv == [
        "claude", "--print", "--output-format", "stream-json", "--verbose", "--bare",
        "--model", "haiku",
        "--tools", "Read,Write,Edit",
        "--allowedTools", "Read(./**) Write(./**) Edit(./**)",
        "--permission-mode", "dontAsk",
        "--max-budget-usd", "1.25",
        "--json-schema", SCHEMA,
        "--resume", str(SID),
        "--append-system-prompt", "You are a builder.",
        "Implement the task in BRIEF.md.",
    ]  # fmt: skip


def test_schema_argument_is_valid_json_with_the_three_statuses():
    argv = build_command(spec(), api_key=False)
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["properties"]["status"]["enum"] == ["done", "continuing", "blocked"]


def test_no_shell_tool_is_ever_offered():
    argv = build_command(spec(), api_key=False)
    assert "Bash" not in argv[argv.index("--tools") + 1]
    assert "Bash" not in argv[argv.index("--allowedTools") + 1]


@pytest.mark.parametrize(
    "bad",
    [
        {"cap_cents": 0},
        {"cap_cents": -5},
        {"cap_cents": 0.5},
        {"cap_cents": True},
        {"prompt": "   "},
        {"prompt": "--dangerously-skip-permissions"},
        {"model": ""},
        {"session_id": "12345678-1234-5678-1234-567812345678"},
    ],
    ids=str,
)
def test_invalid_specs_are_rejected(bad):
    with pytest.raises(ValueError):
        spec(**bad)


def test_worker_env_keeps_only_the_allowlist():
    parent = {
        "HOME": "/home/u",
        "PATH": "/usr/bin",
        "USER": "u",
        "AWS_SECRET_ACCESS_KEY": "x",
        "GITHUB_TOKEN": "y",
        "ANTHROPIC_BASE_URL": "http://proxy",
        "CLAUDECODE": "1",
    }
    assert worker_env(parent) == {"HOME": "/home/u", "PATH": "/usr/bin", "USER": "u"}


def test_api_key_is_passed_through_only_when_set_and_decides_billing():
    with_key = {"HOME": "/h", "ANTHROPIC_API_KEY": "sk-ant-test"}
    assert worker_env(with_key)["ANTHROPIC_API_KEY"] == "sk-ant-test"
    assert billing_mode(with_key) is Billing.API
    assert "ANTHROPIC_API_KEY" not in worker_env({"HOME": "/h", "ANTHROPIC_API_KEY": ""})
    assert billing_mode({"HOME": "/h"}) is Billing.SUBSCRIPTION
