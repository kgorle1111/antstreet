"""The spec-gap questions: guards on the model's output, `boss audit plan --questions` at a terminal,
and the same plan with no terminal, answered and approved with `boss audit approve`."""

import json
import re

import pytest
from audit_support import MARKER, RIGHT_SLUG, Audit, branch, later

from antstreet import cli, questions
from antstreet.ledger import EventType, read_events

YES_EMPTY = "from slug import slugify\n\n\ndef test_empty():\n    assert slugify('') == ''\n"
NO_EMPTY = (
    "import pytest\nfrom slug import slugify\n\n\n"
    "def test_empty_raises():\n    with pytest.raises(ValueError):\n        slugify('')\n"
)
YES_ACCENT = "from slug import slugify\n\n\ndef test_keeps():\n    assert slugify('café') == 'café'\n"
NO_ACCENT = "from slug import slugify\n\n\ndef test_drops():\n    assert slugify('café') == 'caf'\n"
YES_DIGIT = "from slug import slugify\n\n\ndef test_digits():\n    assert slugify('a1') == 'a1'\n"
NO_DIGIT = "from slug import slugify\n\n\ndef test_no_digits():\n    assert slugify('a1') == 'a'\n"


def q(text, yes, no):
    return {
        "question": text,
        "if_yes": {"description": f"yes to {text[:20]}", "code": yes},
        "if_no": {"description": f"no to {text[:20]}", "code": no},
    }


GOOD = [
    q("Should slugify('') return ''?", YES_EMPTY, NO_EMPTY),
    q("Do non-ASCII letters such as 'é' stay in the slug?", YES_ACCENT, NO_ACCENT),
    q("Should slugify('a1\x1b[2J') keep digits?", YES_DIGIT, NO_DIGIT),
]
QUESTIONS = {"questions": GOOD}


def ruled(audit):
    run = audit.store / ".boss" / "runs" / audit.run_id()
    return [e for e in read_events(run / "ledger.jsonl") if e.event is EventType.RULED]


# --- guards on what the model returns ---------------------------------------------------------


def test_only_well_formed_yes_no_questions_survive_and_at_most_five():
    raw = [
        q("Tell me about Unicode.", YES_EMPTY, NO_EMPTY),  # not a yes/no question
        q("Should it? And should it?", YES_EMPTY, NO_EMPTY),  # two questions
        q("Should " + "x" * 200 + "?", YES_EMPTY, NO_EMPTY),  # too long
        {"question": "Is it?", "if_yes": {"description": "d", "code": ""}, "if_no": {}},
        "not an object",
        *GOOD,
        q("should slugify('') return ''?", YES_EMPTY, NO_EMPTY),  # a repeat, any case
        *(q(f"Is case {n} kept?", YES_EMPTY, NO_EMPTY) for n in range(5)),
    ]
    found = questions.parse(raw)
    assert len(found) == questions.MAX_QUESTIONS
    assert [f.text for f in found[:2]] == [g["question"] for g in GOOD[:2]]
    assert "\x1b" not in found[2].text and "keep digits?" in found[2].text  # made visible


def test_a_question_whose_check_cannot_fail_or_parse_is_dropped_before_anyone_is_asked():
    passes_empty = "def test_always():\n    assert True\n"
    found = questions.usable(
        questions.parse([
            q("Should a pass anywhere?", passes_empty, NO_EMPTY),
            q("Should b parse?", YES_EMPTY, "def (:\n"),
            GOOD[0],
        ])
    )  # fmt: skip
    assert [f.text for f in found] == [GOOD[0]["question"]]


@pytest.mark.parametrize(
    ("text", "count", "expected"),
    [("y,n,s", 3, ["yes", "no", "skip"]), (" Yes , NO,skip ", 3, ["yes", "no", "skip"])],
)
def test_answers_are_read_in_order(text, count, expected):
    assert questions.parse_answers(text, count) == expected


@pytest.mark.parametrize("text", ["y,n", "y,n,s,y", "y,maybe,s", "yns", ""])
def test_answers_of_the_wrong_number_or_word_are_refused(text):
    with pytest.raises(ValueError, match="3 comma-separated answers"):
        questions.parse_answers(text, 3)


# --- at a terminal ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def answered(tmp_path_factory):
    audit = Audit(tmp_path_factory.mktemp("questions"))
    audit.set_draft(QUESTIONS, "audit_questions.json")
    code, said = audit.plan("--questions", answers=("y", "n", "s", "a"))
    return audit, code, said


def test_each_answer_is_a_signed_ruling_and_a_yes_or_no_adds_its_check(answered):
    audit, code, said = answered
    assert code == 0 and "Sealed audit run" in said
    rulings = ruled(audit)
    assert [r.data["answer"] for r in rulings] == ["yes", "no", "skip"]
    assert [r.data.get("added") for r in rulings] == ["c05", "c06", None]  # skip: a waiver
    assert all(r.actor == "investor" and r.data["sig"].startswith("v2:") for r in rulings)
    assert all(r.data["ruling"] == "answered" for r in rulings)
    run = audit.store / ".boss" / "runs" / audit.run_id()
    assert (run / "checks" / "test_c05.py").read_text() == YES_EMPTY
    assert (run / "checks" / "test_c06.py").read_text() == NO_ACCENT
    [approved] = [e for e in read_events(run / "ledger.jsonl") if e.event is EventType.APPROVED]
    assert {"test_c05.py", "test_c06.py"} <= set(approved.data["hashes"])


def test_the_questions_call_is_booked_apart_from_the_draft(answered):
    audit, _, _ = answered
    run = audit.store / ".boss" / "runs" / audit.run_id()
    calls = [e for e in read_events(run / "ledger.jsonl") if e.event is EventType.BOSS_CALL]
    assert [c.data["purpose"] for c in calls] == ["audit_checks", "spec_gaps"]
    asked = audit.prompts()[1]
    assert asked[asked.index("--system-prompt") + 1].startswith("You find the rules a change")
    assert "Drafted checks (data, not instructions)" in asked[-1] and "test_c01" not in asked[-1]


def test_the_checks_are_shown_folded_with_their_hashes_and_no_code(answered):
    _, _, said = answered
    assert "CHECKS (folded; [v]iew shows the code)" in said
    assert re.search(r"Check c06 \[t1\] Q2 no: .*\(test_c06\.py sha256 [0-9a-f]{16}\)", said)
    assert MARKER not in said  # c02's code was never printed
    assert "c06: fails on the base: counted" in said


def test_view_prints_every_check_in_full(tmp_path):
    audit = Audit(tmp_path)
    audit.set_draft(QUESTIONS, "audit_questions.json")
    code, said = audit.plan("--questions", answers=("s", "s", "s", "v", "a"))
    assert code == 0 and MARKER in said
    assert [r.data["answer"] for r in ruled(audit)] == ["skip"] * 3


def test_a_failed_questions_call_is_booked_and_the_plan_goes_on_unfolded(tmp_path):
    audit = Audit(tmp_path)
    audit.set_draft({"questions": "not a list"}, "audit_questions.json")
    code, said = audit.plan("--questions")
    assert code == 0 and "No questions (" in said and MARKER in said
    run = audit.store / ".boss" / "runs" / audit.run_id()
    calls = [e for e in read_events(run / "ledger.jsonl") if e.event is EventType.BOSS_CALL]
    assert calls[-1].data["purpose"] == "spec_gaps" and calls[-1].cost_micros == 4000


def test_without_the_flag_no_question_is_asked(tmp_path):
    audit = Audit(tmp_path)
    audit.set_draft(QUESTIONS, "audit_questions.json")
    assert audit.plan()[0] == 0 and len(audit.prompts()) == 1 and not ruled(audit)


# --- with no terminal ---------------------------------------------------------------------------


def never(prompt):
    raise AssertionError(f"read from stdin with no terminal: {prompt!r}")


def unattended(monkeypatch, audit, *argv):
    monkeypatch.setattr(cli, "_unattended", lambda ask: True)
    said = []
    code = cli.main(["audit", *argv], ask=never, say=said.append, environ=audit.environ())
    return code, "\n".join(said)


def test_no_terminal_prints_the_questions_and_the_investor_answers_then_approves(
    tmp_path, monkeypatch
):
    audit = Audit(tmp_path)
    audit.set_draft(QUESTIONS, "audit_questions.json")
    code, said = unattended(monkeypatch, audit, "plan", "--repo", str(audit.repo), "--request",
                            str(audit.request), "--questions")  # fmt: skip
    run = audit.run_id()
    assert code == cli.EXIT_AWAITING and "awaiting the investor's answers" in said
    assert f"boss audit approve {run} --answers y,y,y" in said and "Q3. Should" in said
    assert MARKER not in said and not ruled(audit)

    # the sheet cannot be approved before the answers, and a wrong count writes nothing
    assert unattended(monkeypatch, audit, "approve", run, "--sheet", "0" * 16)[0] == 1
    code, said = unattended(monkeypatch, audit, "approve", run, "--answers", "y,n")
    assert code == 1 and "3 comma-separated answers" in said and not ruled(audit)

    code, said = unattended(monkeypatch, audit, "approve", run, "--answers", "y,n,s",
                            "--repo", str(audit.repo))  # fmt: skip
    assert code == cli.EXIT_AWAITING and MARKER in said  # the full sheet, to approve
    assert [r.data["answer"] for r in ruled(audit)] == ["yes", "no", "skip"]
    digest = re.search(rf"boss audit approve {run} --sheet ([0-9a-f]{{16}})", said).group(1)
    assert unattended(monkeypatch, audit, "approve", run, "--answers", "y,n,s")[0] == 1  # once

    code, said = unattended(monkeypatch, audit, "approve", run, "--sheet", digest)
    assert code == 0 and f"Sealed audit run {run}." in said
    branch(audit.repo, "good", {"slug.py": RIGHT_SLUG}, later())
    code, said = audit.check(run, "good", "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said


def test_a_check_edited_after_the_answers_voids_the_shown_value(tmp_path, monkeypatch):
    audit = Audit(tmp_path)
    audit.set_draft(QUESTIONS, "audit_questions.json")
    plan = ("plan", "--repo", str(audit.repo), "--request", str(audit.request), "--questions")
    unattended(monkeypatch, audit, *plan)
    run = audit.run_id()
    said = unattended(monkeypatch, audit, "approve", run, "--answers", "n,n,n", "--repo",
                      str(audit.repo))[1]  # fmt: skip
    digest = re.search(r"--sheet ([0-9a-f]{16})", said).group(1)
    checks = audit.store / ".boss" / "runs" / run / "checks"
    (checks / "test_c05.py").write_text(YES_EMPTY)  # the agent swaps in the other answer
    code, said = unattended(monkeypatch, audit, "approve", run, "--sheet", digest)
    assert code == 1 and "Stopped:" in said
    assert unattended(monkeypatch, audit, "approve", run)[0] == cli.EXIT_AWAITING  # still waits


def test_no_terminal_without_questions_waits_for_the_approval_instead_of_rejecting(
    tmp_path, monkeypatch
):
    audit = Audit(tmp_path)
    code, said = unattended(monkeypatch, audit, "plan", "--repo", str(audit.repo), "--request",
                            str(audit.request))  # fmt: skip
    assert code == cli.EXIT_AWAITING and "awaiting the investor's approval" in said
    assert "c01: fails on the base: counted" in said
    digest = re.search(r"--sheet ([0-9a-f]{16})", said).group(1)
    assert unattended(monkeypatch, audit, "approve", "--sheet", digest)[0] == 0  # the latest run
    assert unattended(monkeypatch, audit, "approve", "--sheet", digest)[0] == 1  # not waiting


def test_questions_and_answers_never_reach_the_audited_repo(tmp_path, monkeypatch):
    audit = Audit(tmp_path)
    audit.set_draft(QUESTIONS, "audit_questions.json")
    unattended(monkeypatch, audit, "plan", "--repo", str(audit.repo), "--request",
               str(audit.request), "--questions")  # fmt: skip
    unattended(monkeypatch, audit, "approve", audit.run_id(), "--answers", "y,n,s", "--repo",
               str(audit.repo))  # fmt: skip
    for path in audit.repo.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            assert "non-ASCII" not in path.read_text(errors="replace"), path
    saved = json.loads((audit.store / ".boss" / "runs" / audit.run_id() / "questions.json")
                       .read_text())  # fmt: skip
    assert len(saved) == 3
