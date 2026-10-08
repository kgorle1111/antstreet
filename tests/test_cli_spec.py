"""`boss fund --spec`: the checks cite the idea's rules, the investor sees the coverage, the ledger
records it. Run against the fake `claude` of test_cli, with a boss that cites rules."""

import json

import pytest
from test_cli import DRAFT, FAKE_CLAUDE

from antstreet import spec
from antstreet.cli import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main
from antstreet.ledger import EventType, read_events

IDEA = "Reverse a string.\n\n1. reverse('ab') returns 'ba'.\n2. A non-string raises `TypeError`."
CITING = {
    "tasks": DRAFT["tasks"],
    "checks": [{**DRAFT["checks"][0], "rules": ["R02"]}],
    "untested": [{"rule": "R03", "reason": "the product is checked by the first one"}],
}
WRONG = {**CITING, "checks": [{**DRAFT["checks"][0], "rules": ["R99"]}], "untested": []}


@pytest.fixture
def boss(tmp_path):
    def make(draft):
        fake = tmp_path / "fake-claude"
        fake.write_text(FAKE_CLAUDE.replace(repr(DRAFT), repr(draft)))
        fake.chmod(0o755)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)

        def run(*argv, answers=("a",)):
            said, replies = [], iter(answers)
            environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
            code = main(
                [*argv, "--dir", str(project)],
                ask=lambda prompt: next(replies),
                say=said.append,
                environ=environ,
            )
            return code, "\n".join(said)

        runs = project / ".boss" / "runs"
        run.runs = lambda: sorted(runs.iterdir()) if runs.exists() else []
        return run

    return make


def test_the_idea_has_the_two_rules_the_tests_assume():
    assert [(r.id, r.scored) for r in spec.split(IDEA).rules] == [
        ("R01", False),
        ("R02", True),
        ("R03", True),
    ]


def test_spec_makes_a_run_with_rules_a_coverage_view_and_a_recorded_summary(boss):
    run = boss(CITING)
    code, output = run("fund", IDEA, "--budget", "0.50", "--spec")
    assert code == EXIT_OK
    assert "SPEC COVERAGE  rules 2 | UNCOVERED 0 | anchored 0 | unanchored 1" in output
    assert "WAIVED BY THE BOSS" in output and "the product is checked by the first one" in output
    [run_dir] = run.runs()
    assert spec.load(run_dir / "rules.json", IDEA.strip()).scorable
    events = read_events(run_dir / "ledger.jsonl")
    boss_call, approved = events[0], events[1]
    assert boss_call.event is EventType.BOSS_CALL
    assert boss_call.data["prompt"] == "term_sheet_v3.md" and boss_call.data["rules"] == 2
    assert boss_call.data["purpose"] == "term_sheet"
    assert approved.event is EventType.APPROVED and "rules.json" in approved.data["hashes"]
    assert approved.data["spec"]["waived"] == ["R03"] and approved.data["spec"]["unanchored"] == 1
    term_sheet = json.loads((run_dir / "term_sheet.json").read_text())
    assert term_sheet["checks"][0]["criteria"] == ["R02"]
    assert EventType.ROUND_CLOSED in [e.event for e in events], "the firm ran with the rules bound"


def test_without_spec_nothing_about_rules_happens(boss):
    run = boss(DRAFT)
    code, output = run("fund", IDEA, "--budget", "0.50")
    assert code == EXIT_OK and "SPEC COVERAGE" not in output
    [run_dir] = run.runs()
    assert not (run_dir / "rules.json").exists()
    events = read_events(run_dir / "ledger.jsonl")
    assert "prompt" not in events[0].data and "spec" not in events[1].data
    assert set(events[1].data["hashes"]) == {"term_sheet", "test_c01.py"}


def test_a_draft_that_cites_a_rule_that_does_not_exist_stops_the_run_and_books_the_spend(boss):
    run = boss(WRONG)
    code, output = run("fund", IDEA, "--budget", "0.50", "--spec")
    assert code == EXIT_FAILED
    assert "R99" in output
    [run_dir] = run.runs()
    events = read_events(run_dir / "ledger.jsonl")
    assert [e.event for e in events] == [EventType.BOSS_CALL, EventType.STOPPED]
    assert events[0].cost_micros == 4000 and events[0].data["prompt"] == "term_sheet_v3.md"


@pytest.mark.parametrize(
    ("extra", "idea", "message"),
    [
        (["--max-tasks", "2"], IDEA, "--max-tasks 1"),
        (["--roles", "system_designer,tester,product_manager"], IDEA, "staged draft"),
        ([], "1.", "no rule in the idea"),
        ([], "\n\n".join(f"Rule number {n} holds." for n in range(60)), "rule by rule"),
    ],
)
def test_spec_is_refused_before_anything_is_spent_when_it_cannot_be_honoured(
    boss, extra, idea, message
):
    run = boss(CITING)
    code, output = run("fund", idea, "--budget", "0.50", "--spec", *extra)
    assert code == EXIT_USAGE and message in output
    assert run.runs() == [], "no run folder, no call, no spend"


def test_the_flag_is_documented_in_the_help_and_off_by_default(capsys):
    with pytest.raises(SystemExit):
        main(["fund", "--help"])
    help_text = capsys.readouterr().out
    assert "--spec" in help_text and "default: off" in help_text


# --- the spec mapper through the real CLI ------------------------------------------------------


def with_mapper(maps):
    """A fake boss that cites R02 from c01 (its assertion is on line 4); the mapper says `maps`."""
    pick = (
        f"({CITING!r} if '\"maps\"' not in argv[argv.index('--json-schema') + 1] "
        f"else {{'maps': {maps!r}}})"
    )
    return FAKE_CLAUDE.replace(repr(DRAFT), pick)


@pytest.fixture
def mapper(tmp_path):
    def make(maps):
        fake = tmp_path / "fake-claude"
        fake.write_text(with_mapper(maps))
        fake.chmod(0o755)
        project = tmp_path / "project"
        project.mkdir(exist_ok=True)

        def run(*argv):
            said = []
            environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
            code = main(
                [*argv, "--dir", str(project)],
                ask=lambda prompt: "a",
                say=said.append,
                environ=environ,
            )
            return code, "\n".join(said), sorted((project / ".boss" / "runs").iterdir())

        return run

    return make


def test_the_mapper_confirming_a_citation_is_a_note_a_booked_call_and_changes_nothing(mapper):
    run = mapper([{"check": "c01", "exercises": [{"rule": "R02", "line": 4}]}])
    code, output, [run_dir] = run(
        "fund", IDEA, "--budget", "0.50", "--spec", "--roles", "spec_mapper"
    )
    assert code == EXIT_OK
    assert "Spec mapper's opinion" in output and "also found asserted in it" in output
    calls = [
        e
        for e in read_events(run_dir / "ledger.jsonl")
        if e.event is EventType.ROLE_CALL and e.actor == "role:spec_mapper"
    ]
    assert len(calls) == 1 and calls[0].data["result"] == "ok" and calls[0].round == 0
    assert "0 citations unconfirmed" in calls[0].data["detail"]
    approved = next(
        e for e in read_events(run_dir / "ledger.jsonl") if e.event is EventType.APPROVED
    )
    assert "mapper" not in json.dumps(approved.data), "the approval is of the checks, not the note"


def test_a_citation_the_mapper_cannot_confirm_is_shown_as_an_overclaim(mapper):
    run = mapper([{"check": "c01", "exercises": []}])
    code, output, [run_dir] = run(
        "fund", IDEA, "--budget", "0.50", "--spec", "--roles", "spec_mapper"
    )
    assert code == EXIT_OK
    assert "CITED, BUT NO ASSERTION FOUND" in output and "R02 -> c01" in output
    [call] = [e for e in read_events(run_dir / "ledger.jsonl") if e.actor == "role:spec_mapper"]
    assert "1 citations unconfirmed" in call.data["detail"]


def test_a_map_that_fails_the_gate_is_booked_failed_and_the_run_goes_on(mapper):
    run = mapper([{"check": "c01", "exercises": [{"rule": "R02", "line": 1}]}])
    code, output, [run_dir] = run(
        "fund", IDEA, "--budget", "0.50", "--spec", "--roles", "spec_mapper"
    )
    assert code == EXIT_OK
    assert "spec_mapper: FAILED" in output and "line 1 is not an assertion" in output
    [call] = [e for e in read_events(run_dir / "ledger.jsonl") if e.actor == "role:spec_mapper"]
    assert call.data["result"] == "failed" and call.cost_micros == 4000, "the spend is booked"


def test_without_spec_the_mapper_makes_no_call_and_says_why(mapper):
    run = mapper([])
    code, output, [run_dir] = run(
        "fund", "Reverse a string.", "--budget", "0.50", "--roles", "spec_mapper"
    )
    assert code == EXIT_OK
    assert "spec_mapper: not run. It reads the idea's rules, which only --spec makes." in output
    assert not [e for e in read_events(run_dir / "ledger.jsonl") if e.actor == "role:spec_mapper"]
