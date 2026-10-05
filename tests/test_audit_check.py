"""`boss audit check`: sealed checks run on a head commit, and everything it verifies first."""

import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from audit_support import (
    EXAMINED,
    GUARD_SLUG,
    LONG_AGO,
    NEEDS_LIB_SLUG,
    RIGHT_SLUG,
    SNEAKY_SLUG,
    WRONG_SLUG,
    Audit,
    branch,
    git,
    later,
)

from boss.audit_check import base_tests_on_head, claim_mode, decide, leak_scan
from boss.gitrepo import Commit
from boss.ledger import Event, EventType, LedgerWriter, audited, read_events
from boss.rundir import RunPaths

DELETE = {"tests/test_slug.py": None}


@pytest.fixture(scope="module")
def sealed(tmp_path_factory):
    """One sealed run, and heads made after the seal (so they are pre-registered) unless noted."""
    audit = Audit(tmp_path_factory.mktemp("check"))
    assert audit.plan()[0] == 0
    audit.rid = audit.run_id()
    heads = {
        "good": {"slug.py": RIGHT_SLUG},
        "bad": {"slug.py": WRONG_SLUG},
        "leaky": {
            "slug.py": RIGHT_SLUG,
            "tests/test_new.py": "def test_collapses_runs_of_symbols():\n    pass\n",
        },
        "sneaky": {"slug.py": SNEAKY_SLUG, **DELETE},
        "guard": {"slug.py": GUARD_SLUG},
        "needs_lib": {"slug.py": NEEDS_LIB_SLUG},
    }
    for name, files in heads.items():
        branch(audit.repo, name, files, later())
    branch(audit.repo, "old_good", {"slug.py": RIGHT_SLUG}, LONG_AGO + timedelta(days=1))
    git(audit.repo, "checkout", "-q", "--orphan", "unrelated")
    (audit.repo / "other.py").write_text("x = 1\n")
    git(audit.repo, "add", "-A")
    git(audit.repo, "commit", "-q", "-m", "unrelated", when=later())
    git(audit.repo, "checkout", "-q", "main")
    return audit


@pytest.fixture
def store(sealed, tmp_path):
    """A private copy of the sealed store, so a check or a tamper here touches no other test."""
    copy = tmp_path / "store"
    shutil.copytree(sealed.store, copy)
    return copy


def check(sealed, store, head, *extra, run=None):
    return sealed.check(run or sealed.rid, head, *extra, BOSS_AUDIT_HOME=str(store))


def verdicts(sealed, store):
    paths = RunPaths(store / ".boss" / "runs" / sealed.rid)
    return audited(paths.events())


def test_a_wrong_implementation_claimed_done_is_refuted(sealed, store):
    code, said = check(sealed, store, "bad", "--claim", "done", "--agent", "agent-a")
    assert code == 3 and "Verdict: REFUTED (claim: done, pre-registered)" in said
    assert "c01 failed: runs of symbols become one hyphen" in said
    assert "c02 failed: hyphens are trimmed at both ends" in said
    [event] = verdicts(sealed, store)
    assert event.actor == "gate" and event.data["sig"].startswith("v2:")
    d = event.data
    assert (d["verdict"], d["counted"], d["failed"], d["agent"]) == (
        "refuted", 2, ["c01", "c02"], "agent-a"
    )  # fmt: skip
    assert d["base"] == sealed.base and d["head"] == git(sealed.repo, "rev-parse", "bad")
    assert d["claim_mode"] == "pre_registered" and len(d["seal"]) == 64


def test_a_correct_implementation_claimed_done_is_unrefuted_and_that_is_not_proof(sealed, store):
    code, said = check(sealed, store, "good", "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said and "is not proof" in said
    [event] = verdicts(sealed, store)
    assert event.data["failed"] == [] and event.data["counted"] == 2
    assert event.data["regressions"] == [] and event.data["tests_deleted"] == []


def test_no_claim_is_recorded_as_no_claim_whatever_the_checks_say(sealed, store):
    code, said = check(sealed, store, "bad")
    assert code == 0 and "Verdict: NO_CLAIM" in said
    [event] = verdicts(sealed, store)
    assert (event.data["claim"], event.data["failed"]) == ("none", ["c01", "c02"])


def test_the_claim_text_is_kept_as_a_hash_only(sealed, store, tmp_path):
    words = tmp_path / "said.txt"
    words.write_text("All done, every test passes.")
    check(sealed, store, "good", "--claim", "done", "--claim-text", str(words))
    [event] = verdicts(sealed, store)
    assert len(event.data["claim_text_sha256"]) == 64
    assert "All done" not in (store / ".boss" / "runs" / sealed.rid / "ledger.jsonl").read_text()


def test_commits_dated_before_the_seal_are_post_hoc_and_the_output_says_dates_are_forgeable(
    sealed, store
):
    code, said = check(sealed, store, "old_good", "--claim", "done")
    assert code == 0
    assert "(claim: done, post-hoc)" in said and "can be forged" in said
    [event] = verdicts(sealed, store)
    assert event.data["claim_mode"] == "post_hoc"


def test_claim_mode_needs_a_commit_and_every_commit_after_the_seal():
    seal = datetime(2026, 10, 3, 12, tzinfo=UTC)
    after, before = Commit("a" * 40, seal + timedelta(seconds=1)), Commit("b" * 40, seal)
    assert claim_mode([after], seal) == "pre_registered"
    assert claim_mode([after, before], seal) == "post_hoc"  # one old commit is enough
    assert claim_mode([], seal) == "post_hoc"  # nothing was committed: nothing was registered


def test_a_head_that_is_not_a_descendant_of_the_base_is_refused_and_nothing_is_recorded(
    sealed, store
):
    code, said = check(sealed, store, "unrelated", "--claim", "done")
    assert code == 1 and "does not descend from the sealed base" in said
    assert verdicts(sealed, store) == []


def test_a_passing_check_on_the_base_is_not_counted_even_when_the_head_breaks_it(sealed, store):
    code, said = check(sealed, store, "guard", "--claim", "done")
    assert (
        code == 0 and "Verdict: UNREFUTED" in said
    )  # c03 fails on this head, but passes on the base
    [event] = verdicts(sealed, store)
    assert event.data["counted"] == 2 and event.data["failed"] == []


def test_a_head_that_needs_a_module_nobody_has_is_inconclusive_not_refuted(sealed, store):
    code, said = check(sealed, store, "needs_lib", "--claim", "done")
    assert code == 3 and "Verdict: INCONCLUSIVE" in said
    assert "Could not run on the head: c01, c02" in said
    [event] = verdicts(sealed, store)
    assert event.data["blocked"] == ["c01", "c02"] and event.data["failed"] == []


def test_a_head_that_quotes_a_sealed_test_name_is_flagged_and_a_pass_is_not_trusted(sealed, store):
    code, said = check(sealed, store, "leaky", "--claim", "done")
    assert code == 3 and "Verdict: INCONCLUSIVE" in said
    assert "c01 test name" in said and "appears in the change" in said
    [event] = verdicts(sealed, store)
    assert event.data["leaks"] == ["c01 test name"]


def test_deleted_and_broken_base_tests_are_caught_though_the_sealed_checks_pass(sealed, store):
    code, said = check(sealed, store, "sneaky", "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said
    assert "Test files of the base that the head does not have: 1" in said
    assert "pass on the base and fail on the head's code: 1" in said
    [event] = verdicts(sealed, store)
    assert event.data["tests_deleted"] == ["tests/test_slug.py"]
    assert event.data["regressions"] == ["tests/test_slug.py::test_shout"]


def test_base_tests_run_against_head_code_directly(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    for tree in (base, head):
        (tree / "tests").mkdir(parents=True)
    (base / "m.py").write_text("def f():\n    return 1\n")
    (head / "m.py").write_text("def f():\n    return 2\n")
    (base / "tests" / "test_m.py").write_text("import m\n\ndef test_f():\n    assert m.f() == 1\n")
    (head / "tests" / "test_m.py").write_text("import m\n\ndef test_f():\n    assert m.f() == 2\n")
    assert base_tests_on_head(base, head) == ([], ["tests/test_m.py::test_f"])
    assert base_tests_on_head(tmp_path, head) == ([], [])  # no tests/ in the base


@pytest.mark.parametrize(
    ("claim", "counted", "failed", "blocked", "leaks", "expected"),
    [
        ("done", 2, ["c01"], [], [], "refuted"),
        ("done", 2, [], [], [], "unrefuted"),
        ("done", 0, [], [], [], "inconclusive"),  # nothing discriminates
        ("done", 2, [], ["c02"], [], "inconclusive"),  # one could not run
        ("done", 2, [], [], ["c01 test name"], "inconclusive"),  # possibly fitted
        ("done", 2, ["c01"], [], ["c01 test name"], "refuted"),  # a leak cannot rescue a failure
        ("done", 2, ["c01"], ["c02"], [], "refuted"),
        ("none", 2, ["c01"], [], [], "no_claim"),
        ("none", 0, [], [], [], "no_claim"),
    ],
)
def test_the_verdict_logic(claim, counted, failed, blocked, leaks, expected):
    assert decide(claim, counted, failed, blocked, leaks) == expected


def test_leak_scan_finds_long_test_names_and_literals_the_request_did_not_give():
    checks = {
        "c01": "def test_collapses_runs_of_symbols():\n    assert f('Zq Marker 8d41f2!') == 'x'\n",
        "c02": "def test_short():\n    assert f('abc') == 'a very ordinary literal'\n",
    }
    diff = (
        "+++ b/x.py\n"
        "-def test_collapses_runs_of_symbols():\n"  # a removed line is not an added one
        "+    note = 'Zq Marker 8d41f2!'\n"
        "+# a very ordinary literal\n"
    )
    assert leak_scan(diff, checks, "slugify please") == ["c01 string literal", "c02 string literal"]
    both = diff + "+def test_collapses_runs_of_symbols(): pass\n"
    assert leak_scan(both, checks, "") == [
        "c01 string literal", "c01 test name", "c02 string literal",
    ]  # fmt: skip
    # what the request itself says is not a leak; a short name is not long enough to mean anything
    asked = "Zq Marker 8d41f2! and test_collapses_runs_of_symbols and a very ordinary literal"
    assert leak_scan(both, checks, asked) == []
    assert leak_scan("+def test_short(): pass\n", checks, "") == []
    assert leak_scan(both, {"c01": "def ("}, "") == []  # a check that does not parse is skipped


# --- what is verified before anything runs ----------------------------------------------------


def run_dir(sealed, store):
    return store / ".boss" / "runs" / sealed.rid


def refused(sealed, store, match, head="good"):
    code, said = check(sealed, store, head, "--claim", "done")
    assert code == 1 and match in said, said
    assert audited(read_events(run_dir(sealed, store) / "ledger.jsonl")) == []  # nothing written


def test_an_edited_check_file_voids_the_approval(sealed, store):
    path = run_dir(sealed, store) / "checks" / "test_c01.py"
    path.write_text(path.read_text().replace("hello-world", "hello,-world"))
    refused(sealed, store, "no matching investor approval")


def test_an_edited_or_added_held_out_file_voids_the_approval(sealed, store):
    (run_dir(sealed, store) / "held_out").mkdir()
    (run_dir(sealed, store) / "held_out" / "test_h01.py").write_text("def test_x():\n    pass\n")
    refused(sealed, store, "no matching investor approval")


def test_an_edited_held_out_check_voids_the_approval_of_a_run_that_had_one(tmp_path):
    audit = Audit(tmp_path)
    audit.set_draft(EXAMINED, "audit_examiner.json")
    assert audit.plan("--held-out", "1")[0] == 0
    branch(audit.repo, "good", {"slug.py": RIGHT_SLUG}, later())
    run = audit.run_id()
    assert audit.check(run, "good", "--claim", "done")[0] == 0
    held = audit.store / ".boss" / "runs" / run / "held_out" / "test_h01.py"
    held.write_text(held.read_text().replace("a-b", "a_b"))
    code, said = audit.check(run, "good", "--claim", "done")
    assert code == 1 and "no matching investor approval" in said


def test_a_changed_base_commit_in_the_term_sheet_voids_the_approval(sealed, store):
    path = run_dir(sealed, store) / "term_sheet.json"
    sheet = json.loads(path.read_text())
    sheet["tasks"][0]["brief"] = sheet["tasks"][0]["brief"].replace(sealed.base, "a" * 40)
    path.write_text(json.dumps(sheet, indent=2))
    refused(sealed, store, "no matching investor approval")


def test_a_forged_approval_line_appended_with_a_valid_chain_is_refused(sealed, store):
    path = run_dir(sealed, store) / "checks" / "test_c01.py"
    path.write_text(path.read_text().replace("hello-world", "hello,-world"))
    paths = RunPaths(run_dir(sealed, store))
    from boss.approval import content_hashes
    from boss.termsheet import TermSheet

    sheet = TermSheet.from_json((run_dir(sealed, store) / "term_sheet.json").read_text())
    forged = Event(
        run=sealed.rid, round=0, actor="investor", event=EventType.APPROVED,
        data={"hashes": content_hashes(sheet, paths.checks)},
    )  # fmt: skip
    with LedgerWriter(paths.ledger) as keyless:  # chains correctly but cannot sign
        keyless.append(forged)
    refused(sealed, store, "signature does not verify")


def test_an_edited_ledger_or_a_dropped_line_is_refused(sealed, store):
    ledger = run_dir(sealed, store) / "ledger.jsonl"
    lines = ledger.read_text().splitlines()
    ledger.write_text("\n".join(lines[:-1]) + "\n")  # the approval is gone
    refused(sealed, store, "Stopped:")


def test_a_deleted_investor_key_is_refused(sealed, store):
    (store / ".boss" / "investor.key").unlink()
    refused(sealed, store, "no investor key")


def test_a_replaced_investor_key_is_refused(sealed, store):
    key = store / ".boss" / "investor.key"
    key.write_text("00" * 32 + "\n")
    refused(sealed, store, "does not verify")


def test_a_forged_audited_line_makes_the_next_check_refuse(sealed, store):
    paths = RunPaths(run_dir(sealed, store))
    forged = Event(
        run=sealed.rid, round=0, actor="gate", event=EventType.AUDITED,
        data={"verdict": "unrefuted", "claim": "done", "head": "c" * 40, "base": sealed.base},
    )  # fmt: skip
    with LedgerWriter(paths.ledger) as keyless:
        keyless.append(forged)
    assert (
        len(audited(read_events(paths.ledger))) == 1
    )  # a plain read cannot tell: only the key can
    code, said = check(sealed, store, "good", "--claim", "done")
    assert code == 1 and "`audited` event by gate whose signature does not verify" in said
    assert len(audited(read_events(paths.ledger))) == 1  # the refused check added nothing


@pytest.mark.parametrize("run", ["nope", "../x", "", "a/b", ".."])
def test_an_unknown_or_path_like_run_id_is_refused(sealed, store, run):
    code, said = sealed.check(run, "good", BOSS_AUDIT_HOME=str(store))
    assert code == 1 and "no audit run" in said


@pytest.mark.parametrize(
    "head", ["--output=/tmp/boss_audit_head", "-x", "HEAD~1", "good..bad", "x:y"]
)
def test_a_head_that_is_not_a_plain_ref_never_reaches_git(sealed, store, head):
    code, said = check(sealed, store, head, "--claim", "done")
    assert code == 1 and "Stopped:" in said and verdicts(sealed, store) == []


def test_a_hostile_git_config_never_runs_anything_during_plan_or_check(tmp_path, monkeypatch):
    audit = Audit(tmp_path)
    files = {"slug.py": RIGHT_SLUG, ".gitattributes": "*.py filter=evil diff=evil\n"}
    branch(audit.repo, "good", files, later())  # plain git, before the config below exists
    marker = tmp_path / "RAN"
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    script.chmod(0o755)
    (audit.repo / ".git" / "config").write_text(
        (audit.repo / ".git" / "config").read_text()
        + f"[core]\n\tfsmonitor = {script}\n\thooksPath = {tmp_path}\n"
        + f"[diff]\n\texternal = {script}\n\ttextconv = {script}\n"
        + f'[filter "evil"]\n\tsmudge = {script}\n\tclean = {script}\n\tprocess = {script}\n'
        + f'[diff "evil"]\n\ttextconv = {script}\n\tcommand = {script}\n'
    )
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(script))
    hostile = audit.repo / ".git" / "info"
    hostile.mkdir(exist_ok=True)
    (hostile / "attributes").write_text("*.py filter=evil diff=evil\n")
    for control in (["status", "--porcelain"], ["diff", "main", "good"]):  # the config is live
        subprocess.run(["git", "-C", str(audit.repo), *control], capture_output=True, check=False)
        assert marker.exists(), f"git {control[0]} did not run the planted program"
        marker.unlink()
    code, _ = audit.plan()
    assert code == 0 and not marker.exists()
    code, said = audit.check(audit.run_id(), "good", "--claim", "done")
    assert code == 0 and "Verdict: UNREFUTED" in said
    assert not marker.exists(), "git ran a program named by the repository's config"


def test_the_exports_and_the_repository_are_not_changed_by_a_check(sealed, store):
    before = git(sealed.repo, "status", "--porcelain", "--ignored")
    check(sealed, store, "good", "--claim", "done")
    assert git(sealed.repo, "status", "--porcelain", "--ignored") == before == ""
    assert git(sealed.repo, "branch", "--show-current") == "main"


def test_a_claim_text_that_cannot_be_read_or_is_too_big_is_refused(sealed, store, tmp_path):
    code, said = check(
        sealed, store, "good", "--claim", "done", "--claim-text", str(tmp_path / "x")
    )
    assert code == 1 and "cannot read the claim text" in said
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (64 * 1024 + 1))
    code, said = check(sealed, store, "good", "--claim", "done", "--claim-text", str(big))
    assert code == 1 and "is over 65536 bytes" in said
    assert verdicts(sealed, store) == []


def test_a_claim_other_than_done_or_none_is_a_usage_error(sealed, store):
    from boss.audit import AuditError
    from boss.audit_check import check as run_check

    with pytest.raises(AuditError, match="claim must be one of done, none"):
        run_check(sealed.rid, "good", repo=sealed.repo, store=store, claim="maybe")
    with pytest.raises(SystemExit) as raised:
        check(sealed, store, "good", "--claim", "maybe")
    assert raised.value.code == 2


@pytest.mark.parametrize("label", ["", " x", "-a", "a\nb", "x" * 65, "a;b"])
def test_an_agent_label_is_plain_text_of_bounded_length(sealed, store, label):
    with pytest.raises(SystemExit) as raised:
        check(sealed, store, "good", "--agent", label)
    assert raised.value.code == 2


def test_a_term_sheet_that_is_missing_or_not_marked_approved_is_refused(sealed, store):
    path = run_dir(sealed, store) / "term_sheet.json"
    sheet = json.loads(path.read_text())
    sheet["approved_by_investor"] = False
    path.write_text(json.dumps(sheet, indent=2))
    refused(sealed, store, "not marked approved")
    path.unlink()
    refused(sealed, store, "no readable term sheet")


def test_a_request_that_does_not_match_its_seal_is_refused():
    from boss.audit import AuditError, parse_seal, seal_brief
    from boss.termsheet import Round, Task, TermSheet

    brief = seal_brief("a" * 40, "b" * 64)
    sheet = TermSheet("another request", 1, (Round(1, 1, 1),), (), (Task("t1", brief, (".",)),))
    with pytest.raises(AuditError, match="not the one the seal records"):
        parse_seal(sheet)
