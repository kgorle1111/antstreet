"""`boss fund` with no terminal to ask on (Claude Code's Bash tool, a pipe): the paid-for draft
waits for `boss approve`, which records the investor's approval of exactly the text shown, and
`boss resume` builds it. Run against the fake `claude` of test_cli."""

import io
import json
import re
import sys

import pytest
from test_cli import DRAFT, FAKE_CLAUDE
from test_cli_spec import CITING, IDEA

from boss.approval import content_hashes
from boss.cli import AWAITING, EXIT_AWAITING, EXIT_FAILED, EXIT_OK, main
from boss.ledger import EventType, read_events
from boss.signing import SIG_KEY
from boss.termsheet import TermSheet


class Stdin(io.StringIO):
    def __init__(self, text: str, tty: bool) -> None:
        super().__init__(text)
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


@pytest.fixture
def boss(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()

    def run(*argv, stdin="", tty=False, ask=input, draft=DRAFT):
        fake = tmp_path / "fake-claude"
        fake.write_text(FAKE_CLAUDE.replace(repr(DRAFT), repr(draft)))
        fake.chmod(0o755)
        monkeypatch.setattr(sys, "stdin", Stdin(stdin, tty))
        said: list[str] = []
        environ = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "BOSS_CLAUDE_BIN": str(fake)}
        code = main([*argv, "--dir", str(project)], ask=ask, say=said.append, environ=environ)
        return code, "\n".join(said)

    run.project = project
    run.home = tmp_path
    run.runs = lambda: sorted((project / ".boss" / "runs").iterdir())
    return run


def events(boss):
    [run_dir] = boss.runs()
    return read_events(run_dir / "ledger.jsonl")


def digest(output: str) -> str:
    [found] = set(re.findall(r"--sheet ([0-9a-f]{16})", output))
    return found


def test_fund_with_no_terminal_keeps_the_paid_draft_waiting_instead_of_rejecting_it(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    assert code == EXIT_AWAITING
    [run_dir] = boss.runs()
    assert f"boss approve {run_dir.name} --sheet {digest(output)}" in output
    assert "TERM SHEET" in output and "reverse('ab') == 'ba'" in output  # the checks, in full
    assert "Rejected" not in output
    kinds = [e.event for e in events(boss)]
    assert kinds == [EventType.BOSS_CALL, EventType.STARTED, EventType.STOPPED]
    assert events(boss)[-1].data["reason"] == AWAITING
    assert json.loads((run_dir / "term_sheet.json").read_text())["approved_by_investor"] is False
    assert not (boss.home / "worker_argv.txt").exists()  # no worker was hired


def test_approve_records_the_shown_sheet_on_the_signed_ledger_and_resume_builds_it(boss):
    _, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    [run_dir] = boss.runs()
    run = run_dir.name
    before = len(events(boss))
    code, shown = boss("approve", run)  # read it again, at your own prompt: writes nothing
    assert code == EXIT_OK and digest(shown) == digest(output)
    assert len(events(boss)) == before
    code, said = boss("approve", run, "--sheet", digest(output))
    assert code == EXIT_OK and f"boss resume {run}" in said
    approved = events(boss)[-1]
    assert approved.event is EventType.APPROVED and approved.actor == "investor"
    assert approved.data["shown_sha256"].startswith(digest(output))
    assert SIG_KEY in approved.data
    sheet = TermSheet.from_json((run_dir / "term_sheet.json").read_text())
    assert sheet.approved_by_investor is True
    assert approved.data["hashes"] == content_hashes(sheet, run_dir / "checks")
    code, said = boss("resume", run)
    assert code == EXIT_OK and "Round 1: 1/1 checks passed" in said
    kinds = [e.event for e in events(boss)]
    assert kinds.count(EventType.BOSS_CALL) == 1 and kinds.count(EventType.STARTED) == 1
    assert kinds.count(EventType.HIRED) == 1
    code, said = boss("approve", run, "--sheet", digest(output))  # once only
    assert code == EXIT_FAILED and "is not " + AWAITING in said


def test_approve_refuses_a_sheet_changed_since_it_was_shown_and_resume_builds_nothing(boss):
    _, output = boss("fund", "Reverse a string.", "--budget", "0.50")
    [run_dir] = boss.runs()
    before = events(boss)
    check = run_dir / "checks" / "test_c01.py"
    check.write_text(check.read_text().replace("'ab') == 'ba'", "'abc') == 'cba'"))
    code, said = boss("approve", run_dir.name, "--sheet", digest(output))
    assert code == EXIT_FAILED and "Nothing was written" in said
    code, said = boss("approve", run_dir.name, "--sheet", "0" * 16)
    assert code == EXIT_FAILED
    assert events(boss) == before
    assert json.loads((run_dir / "term_sheet.json").read_text())["approved_by_investor"] is False
    code, said = boss("resume", run_dir.name)
    assert code == EXIT_FAILED and AWAITING in said
    assert events(boss) == before and not (boss.home / "worker_argv.txt").exists()
    code, shown = boss("approve", run_dir.name)  # what is there now gets a value of its own
    assert code == EXIT_OK and digest(shown) != digest(output) and "'cba'" in shown


def test_approve_refuses_a_run_fund_did_not_leave_waiting(boss):
    code, _ = boss("fund", "Reverse a string.", "--budget", "0.50", ask=lambda _: "r")
    assert code == EXIT_FAILED
    before = events(boss)
    code, said = boss("approve", "--sheet", "0" * 16)
    assert code == EXIT_FAILED and "is not " + AWAITING in said
    assert events(boss) == before


def test_a_terminal_still_gets_the_question_and_an_answered_ask_never_waits(boss):
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", stdin="a\n", tty=True)
    assert code == EXIT_OK and "--sheet" not in output
    approved = next(e for e in events(boss) if e.event is EventType.APPROVED)
    assert "shown_sha256" not in approved.data
    # The bench, and every caller that answers for itself, is not waited on without a terminal.
    code, output = boss("fund", "Reverse a string.", "--budget", "0.50", ask=lambda _: "a")
    assert code == EXIT_OK and "--sheet" not in output


def test_the_value_fund_prints_approves_a_spec_run_with_the_boss_waivers(boss):
    code, output = boss("fund", IDEA, "--budget", "0.50", "--spec", draft=CITING)
    assert code == EXIT_AWAITING and "the product is checked by the first one" in output
    [run_dir] = boss.runs()
    code, _ = boss("approve", run_dir.name, "--sheet", digest(output), draft=CITING)
    assert code == EXIT_OK
    assert "spec" in events(boss)[-1].data and "rules.json" in events(boss)[-1].data["hashes"]


def test_the_value_fund_prints_approves_a_dispatch_run(boss):
    argv = ("fund", "Reverse a string.", "--budget", "0.50", "--dispatch", "rules")
    code, output = boss(*argv, "--model", "haiku")
    assert code == EXIT_AWAITING
    code, _ = boss("approve", boss.runs()[0].name, "--sheet", digest(output))
    assert code == EXIT_OK and "route" in events(boss)[-1].data
