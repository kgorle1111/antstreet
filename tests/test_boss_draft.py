"""Term-sheet drafting against a fake CLI whose output reuses the recorded boss-call result."""

import json
import sys
from pathlib import Path

import pytest

from boss.boss import DRAFT_SCHEMA, BossError, build_boss_command, draft_term_sheet, load_prompt
from boss.errors import Outcome
from boss.termsheet import TermSheet, TermSheetError

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "json_boss_schema_call_2.1.285.json").read_text()
)
CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [
        {"description": "reverses a word", "task": "t1", "code": CHECK},
        {
            "description": "empty string",
            "task": "t1",
            "code": "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n",
        },
    ],
}
FAKE_CLI = f"""#!{sys.executable}
import json, os, sys, time
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(sys.argv))
if os.environ.get("FAKE_SLEEP"):
    time.sleep(60)
print(os.environ["FAKE_OUTPUT"])
"""


def result_with(**changes) -> dict:
    return RECORDED | {"structured_output": DRAFT} | changes


@pytest.fixture
def draft(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    argv_file = tmp_path / "argv.txt"

    def run(output, *, timeout_s=30.0, **env_extra):
        text = output if isinstance(output, str) else json.dumps(output)
        env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "FAKE_ARGV": str(argv_file),
            "FAKE_OUTPUT": text,
            **env_extra,
        }
        return draft_term_sheet(
            "Reverse a string.",
            500_000,
            tmp_path / "checks",
            env=env,
            timeout_s=timeout_s,
            executable=str(cli),
        )

    run.argv_file = argv_file
    run.checks_dir = tmp_path / "checks"
    return run


def test_valid_draft_becomes_a_validated_term_sheet(draft):
    result = draft(result_with())
    sheet = result.sheet
    assert [c.id for c in sheet.checks] == ["c01", "c02"]
    assert [c.file for c in sheet.checks] == ["test_c01.py", "test_c02.py"]
    assert (draft.checks_dir / "test_c01.py").read_text() == CHECK
    assert sheet.rounds[0].budget_micros == 500_000
    assert sheet.rounds[0].unlock_checks == 2
    assert not sheet.approved_by_investor
    assert result.usage.cost_micros == 3634  # the recorded call's cost, $0.003634
    assert TermSheet.from_json(sheet.to_json()) == sheet


def test_the_call_runs_isolated_with_no_tools(draft):
    draft(result_with())
    argv = json.loads(draft.argv_file.read_text())
    assert "--safe-mode" in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--system-prompt") + 1] == load_prompt("term_sheet_v1.md")
    assert argv[-1] == "Idea:\nReverse a string."


def test_failed_call_raises_with_its_outcome(draft):
    login = RECORDED | {"is_error": True, "api_error_status": 401, "terminal_reason": "api_error"}
    with pytest.raises(BossError) as info:
        draft(login)
    assert info.value.outcome is Outcome.LOGIN


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"structured_output": None}, "no structured output"),
        ({"structured_output": {"tasks": DRAFT["tasks"]}}, "missing or malformed"),
        ({"structured_output": DRAFT | {"tasks": DRAFT["tasks"] * 2}}, "exactly one task"),
        ({"structured_output": DRAFT | {"checks": []}}, "expected 1 to 8 checks"),
        (
            {"structured_output": DRAFT | {"tasks": [DRAFT["tasks"][0] | {"paths": "rev.py"}]}},
            "missing or malformed",
        ),
        (
            {
                "structured_output": DRAFT
                | {"checks": [{"description": "d", "task": "t1", "code": 7}]}
            },
            "code is not text",
        ),
    ],
    ids=["none", "no-checks-key", "two-tasks", "zero-checks", "paths-string", "code-not-text"],
)
def test_unusable_drafts_raise(draft, change, message):
    with pytest.raises(BossError, match=message):
        draft(result_with(**change))


def test_draft_whose_check_passes_on_an_empty_workspace_is_rejected(draft):
    trivial = {"description": "always passes", "task": "t1", "code": "def test_x():\n    pass\n"}
    with pytest.raises(TermSheetError) as info:
        draft(result_with(structured_output=DRAFT | {"checks": [DRAFT["checks"][0], trivial]}))
    assert info.value.problems == ["check c02 passes on an empty workspace"]


def test_garbage_output_is_a_crash(draft):
    with pytest.raises(BossError) as info:
        draft("this is not json")
    assert info.value.outcome is Outcome.CRASHED


def test_timeout(draft):
    with pytest.raises(BossError) as info:
        draft(result_with(), timeout_s=1.0, FAKE_SLEEP="1")
    assert info.value.outcome is Outcome.TIMEOUT


def test_idea_cannot_be_read_as_a_flag(draft):
    with pytest.raises(ValueError):
        draft_term_sheet("--dangerously-skip-permissions", 1, Path("unused"), env={})


def test_command_is_pinned():
    argv = build_boss_command(
        prompt="Idea:\nx",
        system_prompt="S",
        schema={"type": "object"},
        model="haiku",
        cap_micros=100_000,
        api_key=True,
    )
    assert argv == [
        "claude", "--print", "--output-format", "json", "--bare", "--model", "haiku",
        "--tools", "", "--system-prompt", "S", "--json-schema", '{"type":"object"}',
        "--max-budget-usd", "0.1", "Idea:\nx",
    ]  # fmt: skip


def test_schema_caps_tasks_and_checks():
    assert DRAFT_SCHEMA["properties"]["tasks"]["maxItems"] == 1
    assert DRAFT_SCHEMA["properties"]["checks"]["maxItems"] == 8
