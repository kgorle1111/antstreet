"""action.yml, the composite GitHub Action, stays safe and true to the CLI: it runs only the free
offline `audit check`, never a step that spends or approves, and every antstreet call it makes
parses with the real argument parser."""

import re
import shlex

import pytest
import yaml
from docs_support import ROOT

from antstreet import cli

ACTION = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
STEPS = ACTION["runs"]["steps"]
SCRIPTS = [s["run"] for s in STEPS if "run" in s]
FORBIDDEN = ("fund", "resume", "topup", "approve", "plan")
CALL = re.compile(r"uvx .*? antstreet (?P<args>[^\n|]*?)\s*2>&1")


def test_it_is_a_composite_action_with_every_run_step_naming_its_shell():
    assert ACTION["runs"]["using"] == "composite"
    assert all(s["shell"] == "bash" for s in STEPS if "run" in s)


def test_third_party_actions_are_pinned_by_commit():
    uses = [s["uses"] for s in STEPS if "uses" in s]
    assert uses
    assert all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) for u in uses), uses


def test_every_antstreet_call_is_a_real_subcommand_and_only_audit_check():
    calls = [m for script in SCRIPTS for m in CALL.finditer(script)]
    assert len(calls) == 1
    # shell variables stand in for values; the parser sees the shape
    argv = shlex.split(calls[0]["args"].replace('"', ""))
    args = cli._parser().parse_args(
        [a.replace("$RUN_ID", "r1").replace("$HEAD_REF", "h").replace("$REPO", ".") for a in argv]
    )
    assert (args.command, args.audit_command, args.claim) == ("audit", "check", "done")


@pytest.mark.parametrize("word", FORBIDDEN)
def test_no_step_runs_a_command_that_spends_or_approves(word):
    for script in SCRIPTS:
        assert not re.search(rf"antstreet\s+(audit\s+)?{word}\b", script)
        assert not re.search(rf"\bboss\s+(audit\s+)?{word}\b", script)
    assert "--live" not in "\n".join(SCRIPTS)


def test_the_sandbox_is_required_on_linux_and_bubblewrap_is_installed():
    check = next(s for s in STEPS if s.get("id") == "check")
    assert "'require'" in check["env"]["BOSS_GATE_SANDBOX"]
    assert any("bubblewrap" in s["run"] for s in STEPS if "run" in s)


def test_inputs_reach_scripts_through_env_never_spliced_into_them():
    assert not any("inputs." in script or "github." in script for script in SCRIPTS)


def test_it_writes_the_job_summary_and_fails_with_the_cli_exit_code():
    script = next(s["run"] for s in STEPS if s.get("id") == "check")
    assert "GITHUB_STEP_SUMMARY" in script
    assert 'exit "$code"' in script


def test_the_documented_inputs_match_the_action():
    text = (ROOT / "README-technical.md").read_text(encoding="utf-8")
    for name in ACTION["inputs"]:
        assert f"| `{name}` |" in text
