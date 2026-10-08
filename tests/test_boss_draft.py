"""Term-sheet drafting against a fake CLI whose output reuses the recorded boss-call result."""

import json
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT_LINE

from antstreet.boss import (
    DRAFT_SCHEMA,
    BossError,
    InvalidDraftError,
    build_boss_command,
    draft_schema,
    draft_term_sheet,
    load_prompt,
)
from antstreet.errors import Outcome
from antstreet.termsheet import TermSheet

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
UP_CHECK = "from up import shout\n\ndef test_shout():\n    assert shout('ab') == 'AB'\n"
TWO_TASKS = {
    "tasks": [
        {"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]},
        {"id": "t2", "brief": "Create up.py with shout(s).", "paths": ["up.py"]},
    ],
    "checks": [
        {"description": "reverses a word", "task": "t1", "code": CHECK},
        {"description": "shouts a word", "task": "t2", "code": UP_CHECK},
    ],
}
FAKE_CLI = f"""#!{sys.executable}
import json, os, sys, time
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(sys.argv))
thinking = os.environ.get("MAX_THINKING_TOKENS", "unset")
open(os.environ["FAKE_ARGV"] + ".thinking", "w").write(thinking)
if os.environ.get("FAKE_SLEEP"):
    time.sleep(60)
print({BOSS_INIT_LINE!r})
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

    def run(output, *, timeout_s=30.0, max_tasks=None, thinking_tokens=None, **env_extra):
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
            thinking_tokens=thinking_tokens,
            **({} if max_tasks is None else {"max_tasks": max_tasks}),
        )

    run.argv_file = argv_file
    run.thinking = lambda: (tmp_path / "argv.txt.thinking").read_text()
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


def test_thinking_budget_reaches_the_call_and_is_off_limits_to_the_callers_environment(draft):
    draft(result_with())
    assert draft.thinking() == "unset"  # by default the CLI decides
    draft(result_with(), thinking_tokens=0)
    assert draft.thinking() == "0"
    draft(result_with(), thinking_tokens=2048, MAX_THINKING_TOKENS="99999")
    assert draft.thinking() == "2048"  # the explicit budget wins over an inherited one


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


def test_draft_whose_check_passes_on_an_empty_workspace_is_rejected_but_still_costed(draft):
    trivial = {"description": "always passes", "task": "t1", "code": "def test_x():\n    pass\n"}
    with pytest.raises(InvalidDraftError) as info:
        draft(result_with(structured_output=DRAFT | {"checks": [DRAFT["checks"][0], trivial]}))
    assert info.value.problems == ["check c02 passes on an empty workspace"]
    assert info.value.usage.cost_micros == 3634  # the call was paid for; the ledger must see it


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
        "claude", "--print", "--output-format", "stream-json", "--verbose", "--bare",
        "--model", "haiku", "--tools", "", "--permission-mode", "dontAsk",
        "--system-prompt", "S", "--json-schema", '{"type":"object"}',
        "--max-budget-usd", "0.1", "Idea:\nx",
    ]  # fmt: skip


def test_schema_caps_tasks_and_checks():
    assert DRAFT_SCHEMA["properties"]["tasks"]["maxItems"] == 1
    assert DRAFT_SCHEMA["properties"]["checks"]["maxItems"] == 8


def test_two_task_draft_with_room_for_two_becomes_a_validated_sheet(draft):
    sheet = draft(result_with(structured_output=TWO_TASKS), max_tasks=2).sheet
    assert [t.id for t in sheet.tasks] == ["t1", "t2"]
    assert [(c.id, c.task) for c in sheet.checks] == [("c01", "t1"), ("c02", "t2")]
    assert [c.file for c in sheet.checks] == ["test_c01.py", "test_c02.py"]
    assert (draft.checks_dir / "test_c02.py").read_text() == UP_CHECK
    assert sheet.rounds[0].budget_micros == 500_000
    assert TermSheet.from_json(sheet.to_json()) == sheet


def test_two_task_draft_is_unusable_by_default(draft):
    with pytest.raises(BossError, match="unusable draft: expected exactly one task, got 2"):
        draft(result_with(structured_output=TWO_TASKS))


def test_more_tasks_than_allowed_is_unusable(draft):
    three = TWO_TASKS["tasks"] + [{"id": "t3", "brief": "b", "paths": ["z.py"]}]
    with pytest.raises(BossError, match="unusable draft: expected 1 to 2 tasks, got 3"):
        draft(result_with(structured_output=TWO_TASKS | {"tasks": three}), max_tasks=2)


def test_no_tasks_is_unusable_even_when_several_are_allowed(draft):
    with pytest.raises(BossError, match="unusable draft: expected 1 to 2 tasks, got 0"):
        draft(result_with(structured_output=TWO_TASKS | {"tasks": []}), max_tasks=2)


def test_several_tasks_use_the_v2_prompt_and_state_the_limit_in_the_user_prompt(draft):
    draft(result_with(structured_output=TWO_TASKS), max_tasks=2)
    argv = json.loads(draft.argv_file.read_text())
    system = argv[argv.index("--system-prompt") + 1]
    assert system == load_prompt("term_sheet_v2.md")
    assert system != load_prompt("term_sheet_v1.md")
    assert "2" not in system.split("Tasks")[0]  # the limit lives in the user prompt only
    assert argv[-1] == "Idea:\nReverse a string.\n\nYou may use at most 2 tasks."
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["properties"]["tasks"]["maxItems"] == 2


def test_default_call_is_byte_for_byte_the_single_task_call(draft):
    draft(result_with())
    argv = json.loads(draft.argv_file.read_text())
    assert argv[argv.index("--system-prompt") + 1] == load_prompt("term_sheet_v1.md")
    assert argv[argv.index("--json-schema") + 1] == json.dumps(DRAFT_SCHEMA, separators=(",", ":"))
    assert argv[-1] == "Idea:\nReverse a string."
    draft(result_with(), max_tasks=1)
    assert json.loads(draft.argv_file.read_text()) == argv


def test_tasks_owning_overlapping_paths_are_rejected_but_still_costed(draft):
    tasks = [TWO_TASKS["tasks"][0], TWO_TASKS["tasks"][1] | {"paths": ["./rev.py", "up.py"]}]
    with pytest.raises(InvalidDraftError) as info:
        draft(result_with(structured_output=TWO_TASKS | {"tasks": tasks}), max_tasks=2)
    assert info.value.problems == ["tasks t1 and t2 both own rev.py"]
    assert info.value.usage.cost_micros == 3634


@pytest.mark.parametrize("bad", [0, -1])
def test_max_tasks_below_one_is_a_value_error(draft, bad):
    with pytest.raises(ValueError, match="max_tasks"):
        draft(result_with(), max_tasks=bad)


def test_draft_schema_caps_tasks_at_max_tasks():
    assert draft_schema(3)["properties"]["tasks"]["maxItems"] == 3
    assert draft_schema(1) == DRAFT_SCHEMA
