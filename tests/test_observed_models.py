"""The model a boss or role call actually ran is recorded beside the one it asked for (R2).

`boss_call.model` and `role_call.model` are the requested strings; an alias such as `haiku` or a
silently substituted model would otherwise leave no trace. The CLI names what it started in its
`system/init` event, and that id now travels on `Usage.model_observed` to the ledger and report.
"""

import json
import sys

import pytest
from boss_init import BOSS_INIT
from docs_support import run_cli

from antstreet.boss import BossError, draft_term_sheet
from antstreet.errors import Outcome
from antstreet.ledger import EventType, read_events
from antstreet.roles.base import RoleError, RoleSpec, call_role, ledger_fields
from antstreet.stream import StreamReader, Usage

RAN = "claude-opus-5-5"
RESULT = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "terminal_reason": "completed",
    "total_cost_usd": 0.01,
    "modelUsage": {"m": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0}},
}
CHECK = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
DRAFT = {
    "tasks": [{"id": "t1", "brief": "Create rev.py with reverse(s).", "paths": ["rev.py"]}],
    "checks": [{"description": "reverses a word", "task": "t1", "code": CHECK}],
}
FAKE = f"""#!{sys.executable}
import json, os
init = json.loads(os.environ["FAKE_INIT"])
if init:
    print(json.dumps(init))
print(os.environ["FAKE_OUTPUT"])
"""


def init_reporting(model: str | None) -> dict:
    init = dict(BOSS_INIT)
    if model is None:
        init.pop("model", None)
    else:
        init["model"] = model
    return init


@pytest.fixture
def fake(tmp_path):
    cli = tmp_path / "fake-claude"
    cli.write_text(FAKE)
    cli.chmod(0o755)

    def env(output: dict, init: dict | None) -> dict[str, str]:
        return {
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "FAKE_INIT": json.dumps(init or {}),
            "FAKE_OUTPUT": json.dumps(output),
        }

    env.cli = str(cli)
    env.checks = tmp_path / "checks"
    return env


# --- the reader ----------------------------------------------------------------------------


def read(*events: dict) -> StreamReader:
    reader = StreamReader()
    for event in events:
        reader.feed(json.dumps(event))
    return reader


def test_the_reader_keeps_the_model_its_init_names():
    usage = read(init_reporting(RAN), RESULT).usage()
    assert usage.model_observed == RAN


def test_no_init_means_no_observed_model():
    assert read(RESULT).usage().model_observed is None
    assert read(init_reporting(None), RESULT).usage().model_observed is None


def test_a_call_killed_before_its_result_still_names_its_model():
    usage = read(init_reporting(RAN)).usage()  # no result: the message-sum path
    assert usage.cost_micros is None and usage.model_observed == RAN


def test_an_observed_model_is_bounded_before_it_can_reach_the_ledger():
    # The same cleaning as a worker's `slice_end.model_id` (`worker.model_id_of`).
    usage = read(init_reporting("claude-" + "y" * 500), RESULT).usage()
    assert usage.model_observed is not None and len(usage.model_observed) <= 110


def test_the_observed_model_is_metadata_and_never_changes_what_equal_usage_means():
    assert Usage(1, 2, 3, 4, model_observed="a") == Usage(1, 2, 3, 4)


# --- the boss's and roles' calls --------------------------------------------------------------


def test_a_boss_draft_carries_the_model_the_cli_ran_not_the_one_requested(fake):
    draft = draft_term_sheet(
        "Reverse a string.",
        500_000,
        fake.checks,
        env=fake(RESULT | {"structured_output": DRAFT}, init_reporting(RAN)),
        model="haiku",
        executable=fake.cli,
    )
    assert draft.usage.model_observed == RAN


def test_a_capped_boss_call_still_says_which_model_was_capped(fake):
    capped = RESULT | {"subtype": "error_max_budget_usd", "terminal_reason": "budget_exhausted"}
    with pytest.raises(BossError) as info:
        draft_term_sheet(
            "Reverse a string.",
            500_000,
            fake.checks,
            env=fake(capped, init_reporting(RAN)),
            model="opus",
            executable=fake.cli,
        )
    assert info.value.outcome is Outcome.CAPPED
    assert info.value.usage.model_observed == RAN


ROLE = RoleSpec("tester", "engineering", "boss", "writes checks", "fails empty", "term_sheet_v1.md")
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}}


def test_a_role_call_and_its_ledger_fields_carry_the_observed_model(fake):
    out = call_role(
        ROLE,
        "Idea:\nx",
        SCHEMA,
        env=fake(RESULT | {"structured_output": {"answer": "ok"}}, init_reporting(RAN)),
        model="haiku",
        executable=fake.cli,
    )
    fields = ledger_fields(ROLE, out.usage, "completed", model="haiku", env={})
    assert (fields["data"]["model"], fields["data"]["model_observed"]) == ("haiku", RAN)


def test_a_failed_role_call_carries_the_observed_model_too(fake):
    with pytest.raises(RoleError) as info:
        call_role(
            ROLE,
            "Idea:\nx",
            SCHEMA,
            env=fake(RESULT | {"structured_output": None}, init_reporting(RAN)),
            model="haiku",
            executable=fake.cli,
        )
    assert info.value.usage.model_observed == RAN


# --- the real CLI, end to end ------------------------------------------------------------------


def test_fund_records_the_observed_boss_model_beside_the_requested_one(tmp_path):
    # The fake CLI's init always says Haiku 4.5, so asking for sonnet shows the two apart.
    _, run_dir, _ = run_cli(
        tmp_path, ["fund", "Reverse a string.", "--budget", "0.50", "--boss-model", "sonnet"]
    )
    events = read_events(run_dir / "ledger.jsonl")
    [call] = [e for e in events if e.event is EventType.BOSS_CALL]
    assert call.data["model"] == "sonnet"
    assert call.data["model_observed"] == BOSS_INIT["model"]


def test_audit_plan_records_the_observed_boss_model_too(tmp_path):
    from audit_support import Audit

    audit = Audit(tmp_path)
    assert audit.plan()[0] == 0
    events = read_events(audit.store / ".boss" / "runs" / audit.run_id() / "ledger.jsonl")
    [call] = [e for e in events if e.event is EventType.BOSS_CALL]
    assert call.data["model_observed"] == BOSS_INIT["model"]
