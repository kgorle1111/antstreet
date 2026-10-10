"""Boss-call edge cases: malformed drafts, failed or missing binaries, and prompt construction."""

import json
import sys
from pathlib import Path

import pytest
from boss_init import BOSS_INIT_LINE

from antstreet.boss import (
    DRAFT_SCHEMA,
    MAX_CHECKS,
    BossError,
    InvalidDraftError,
    build_boss_command,
    draft_schema,
    draft_term_sheet,
    load_prompt,
)
from antstreet.errors import Outcome

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "json_boss_schema_call_2.1.285.json").read_text()
)
COST = 3634  # micro-dollars in the recorded call
CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
TASK = {"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}
GOOD_CHECK = {"description": "reverses a word", "task": "t1", "code": CHECK}
DRAFT = {"tasks": [TASK], "checks": [GOOD_CHECK]}
FAKE_CLI = f"""#!{sys.executable}
import json, os, sys
open(os.environ["FAKE_ARGV"], "w").write(json.dumps(sys.argv))
open(os.environ["FAKE_ARGV"] + ".cwd", "w").write(os.getcwd())
print({BOSS_INIT_LINE!r})
sys.stdout.write(os.environ["FAKE_OUTPUT"])
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


def result_with(**changes) -> dict:
    return RECORDED | {"structured_output": DRAFT} | changes


@pytest.fixture
def draft(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE_CLI)
    cli.chmod(0o755)
    argv_file = tmp_path / "argv.txt"

    def run(output, *, idea="Reverse a string.", env_extra=None, **kwargs):
        text = output if isinstance(output, str) else json.dumps(output)
        env = {"PATH": "/usr/bin:/bin", "FAKE_ARGV": str(argv_file), "FAKE_OUTPUT": text}
        return draft_term_sheet(
            idea,
            500_000,
            tmp_path / "checks",
            env=env | (env_extra or {}),
            executable=kwargs.pop("executable", str(cli)),
            **kwargs,
        )

    run.argv = lambda: json.loads(argv_file.read_text())
    run.cwd = lambda: Path(argv_file.with_name("argv.txt.cwd").read_text())
    run.checks_dir = tmp_path / "checks"
    return run


def with_draft(**changes) -> dict:
    return result_with(structured_output=DRAFT | changes)


# --- malformed drafts ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"tasks": "t1"}, "missing or malformed field: expected a list, got str"),
        ({"tasks": None}, "missing or malformed field: expected a list, got NoneType"),
        ({"checks": {"description": "d"}}, "missing or malformed field: expected a list, got dict"),
        ({"tasks": ["not an object"]}, "missing or malformed field"),
        ({"tasks": [{"id": "t1", "brief": "b"}]}, "missing or malformed field: 'paths'"),
        ({"tasks": [TASK | {"id": 7}]}, "missing or malformed field"),
        ({"tasks": [TASK | {"paths": ["rev.py", 3]}]}, "missing or malformed field"),
        ({"tasks": []}, "expected exactly one task, got 0"),
        ({"checks": [GOOD_CHECK] * (MAX_CHECKS + 1)}, f"expected 1 to {MAX_CHECKS} checks, got 9"),
        ({"checks": ["not an object"]}, "check 1 is malformed"),
        ({"checks": [{"task": "t1", "code": CHECK}]}, "check 1 is malformed: 'description'"),
        ({"checks": [{"description": "d", "task": "t1"}]}, "check 1 is malformed: 'code'"),
        ({"checks": [GOOD_CHECK | {"description": 5}]}, "check 1 is malformed"),
        ({"checks": [GOOD_CHECK, GOOD_CHECK | {"code": None}]}, "check 2 code is not text"),
    ],
    ids=[
        "tasks-string",
        "tasks-null",
        "checks-dict",
        "task-not-object",
        "task-missing-paths",
        "task-id-int",
        "path-int",
        "zero-tasks",
        "nine-checks",
        "check-not-object",
        "check-missing-description",
        "check-missing-code",
        "description-int",
        "second-code-null",
    ],
)
def test_malformed_drafts_are_unusable_but_still_costed(draft, changes, message):
    with pytest.raises(BossError, match="unusable draft") as info:
        draft(with_draft(**changes))
    assert message in str(info.value)
    assert info.value.outcome is Outcome.COMPLETED
    assert info.value.usage.cost_micros == COST
    assert not isinstance(info.value, InvalidDraftError)


def test_structured_output_that_is_not_an_object_is_unusable(draft):
    for value in (None, [DRAFT], "text", 7):
        with pytest.raises(BossError, match="no structured output"):
            draft(result_with(structured_output=value))


def test_a_draft_without_structured_output_at_all_is_unusable(draft):
    without = {k: v for k, v in RECORDED.items() if k != "structured_output"}
    with pytest.raises(BossError, match="no structured output"):
        draft(without)


def test_the_check_files_are_named_by_code_never_by_the_model(draft):
    two = [GOOD_CHECK, GOOD_CHECK | {"description": "again", "code": CHECK + "\n"}]
    result = draft(with_draft(checks=two, tasks=[TASK]))
    assert [(c.id, c.file) for c in result.sheet.checks] == [
        ("c01", "test_c01.py"),
        ("c02", "test_c02.py"),
    ]
    assert (draft.checks_dir / "test_c02.py").read_text() == CHECK + "\n"


def test_model_supplied_id_and_file_fields_are_ignored(draft):
    sneaky = GOOD_CHECK | {"id": "../../evil", "file": "../evil.py"}
    result = draft(with_draft(checks=[sneaky]))
    assert result.sheet.checks[0].id == "c01"
    assert result.sheet.checks[0].file == "test_c01.py"
    assert not (draft.checks_dir.parent / "evil.py").exists()


def test_a_check_for_an_unknown_task_is_an_invalid_draft_naming_it(draft):
    with pytest.raises(InvalidDraftError) as info:
        draft(with_draft(checks=[GOOD_CHECK | {"task": "t9"}]))
    assert "check c01 belongs to unknown task 't9'" in info.value.problems
    assert "task t1 owns no checks, so its progress cannot be measured" in info.value.problems
    assert info.value.outcome is Outcome.COMPLETED
    assert info.value.usage.cost_micros == COST
    assert str(info.value).startswith("draft term sheet is invalid: ")


def test_a_check_with_a_syntax_error_is_an_invalid_draft(draft):
    with pytest.raises(InvalidDraftError) as info:
        draft(with_draft(checks=[GOOD_CHECK | {"code": "def test_x(:\n"}]))
    assert [p.split(":")[0] for p in info.value.problems] == ["check c01 has a syntax error"]


def test_a_draft_with_task_paths_leaving_the_workspace_is_invalid(draft):
    bad = TASK | {"paths": ["../outside.py"]}
    with pytest.raises(InvalidDraftError) as info:
        draft(with_draft(tasks=[bad]))
    assert any("must stay inside the workspace" in p for p in info.value.problems)


def test_a_pretty_printed_result_is_not_one_event_per_line_and_is_refused(draft):
    # The old `json` format could be pretty-printed; `stream-json` is one event per line.
    with pytest.raises(BossError) as caught:
        draft(json.dumps(result_with(), indent=2) + "\n")
    assert caught.value.outcome is Outcome.CRASHED


def test_the_idea_is_stripped_and_kept_on_the_sheet(draft):
    result = draft(result_with(), idea="  Reverse a string.  \n")
    assert result.sheet.idea == "Reverse a string."
    assert draft.argv()[-1] == "Idea:\nReverse a string."


# --- failed calls ----------------------------------------------------------------------------


def test_a_nonzero_exit_with_a_good_result_is_judged_by_the_result_not_the_exit(draft):
    result = draft(result_with(), env_extra={"FAKE_EXIT": "1"})
    assert result.usage.cost_micros == COST


def test_a_nonzero_exit_with_no_output_is_a_crash_with_unknown_cost(draft):
    with pytest.raises(BossError) as info:
        draft("", env_extra={"FAKE_EXIT": "3"})
    assert info.value.outcome is Outcome.CRASHED
    assert info.value.usage.cost_micros is None
    assert str(info.value) == "boss call ended as crashed"


def test_a_capped_call_reports_the_cost_it_did_incur(draft):
    capped = result_with(subtype="error_max_budget_usd", is_error=True)
    with pytest.raises(BossError) as info:
        draft(capped)
    assert info.value.outcome is Outcome.CAPPED
    assert info.value.usage.cost_micros == COST


def test_a_missing_executable_is_a_boss_error_the_caller_can_record(draft, tmp_path):
    with pytest.raises(BossError):
        draft(result_with(), executable=str(tmp_path / "no-such-claude"))


def test_an_unstartable_executable_names_itself_points_at_doctor_and_has_unknown_cost(
    draft, tmp_path
):
    plain_file = tmp_path / "not-executable"
    plain_file.write_text("#!/bin/sh\n")
    for executable in (str(tmp_path / "no-such-claude"), str(plain_file)):
        with pytest.raises(BossError) as info:
            draft(result_with(), executable=executable)
        assert executable in str(info.value)
        assert "antstreet doctor" in str(info.value)
        assert info.value.usage.cost_micros is None


# --- arguments and prompt --------------------------------------------------------------------


@pytest.mark.parametrize("idea", ["", "   ", "\n\t", "-x", "  --flag", "\n-rf"])
def test_blank_or_flag_like_ideas_are_refused_before_any_call(tmp_path, idea):
    with pytest.raises(ValueError, match="idea must be non-empty"):
        draft_term_sheet(idea, 1, tmp_path / "checks", env={}, executable="/nonexistent")
    assert not (tmp_path / "checks").exists()


def test_an_idea_containing_a_dash_later_is_fine(draft):
    result = draft(result_with(), idea="A to-do list - with dashes")
    assert result.sheet.idea == "A to-do list - with dashes"


def test_model_and_cap_reach_the_command_line(draft):
    draft(result_with(), model="sonnet", cap_micros=40_000)
    argv = draft.argv()
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--max-budget-usd") + 1] == "0.04"


def test_an_api_key_in_the_env_selects_bare_mode(draft):
    draft(result_with(), env_extra={"ANTHROPIC_API_KEY": "sk-ant-test-value"})
    argv = draft.argv()
    assert "--bare" in argv and "--safe-mode" not in argv


def test_the_call_runs_in_a_scratch_directory_that_is_removed_afterwards(draft, tmp_path):
    draft(result_with())
    cwd = draft.cwd()
    assert "boss_call_" in cwd.name
    assert cwd != tmp_path and not cwd.exists()


def test_schema_builder_matches_the_default_and_scales_with_max_tasks():
    assert draft_schema(1) == DRAFT_SCHEMA
    assert draft_schema(5)["properties"]["tasks"]["maxItems"] == 5
    assert draft_schema(5)["properties"]["checks"]["maxItems"] == MAX_CHECKS
    assert draft_schema(3)["required"] == ["tasks", "checks"]


def test_schema_requires_the_fields_the_parser_reads():
    props = DRAFT_SCHEMA["properties"]
    assert props["tasks"]["items"]["required"] == ["id", "brief", "paths"]
    assert props["checks"]["items"]["required"] == ["description", "task", "code"]


def test_api_key_false_command_uses_safe_mode_and_a_fractional_cap():
    argv = build_boss_command(
        prompt="p", system_prompt="s", schema={}, model="m", cap_micros=6_000, api_key=False
    )
    assert "--safe-mode" in argv and "--bare" not in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "0.006"
    assert argv[argv.index("--json-schema") + 1] == "{}"


def test_a_missing_prompt_file_is_a_file_not_found_error():
    with pytest.raises(FileNotFoundError):
        load_prompt("no_such_prompt.md")


@pytest.mark.parametrize("name", ["term_sheet_v1.md", "term_sheet_v2.md"])
def test_shipped_prompts_are_present_and_non_empty(name):
    assert load_prompt(name).strip()
