"""`boss audit plan`: checks sealed from the request and the base's names, kept outside the repo."""

import json
import re
from pathlib import Path

import pytest
from audit_support import (
    DRAFT,
    EXAMINED,
    MARKER,
    REQUEST,
    RIGHT_SLUG,
    Audit,
    branch,
    git,
    later,
)

from boss.audit import (
    AuditError,
    CheckState,
    parse_seal,
    public_surface,
    request_hash,
    store_root,
)
from boss.ledger import EventType, read_events
from boss.termsheet import TermSheet


@pytest.fixture(scope="module")
def planned(tmp_path_factory):
    audit = Audit(tmp_path_factory.mktemp("plan"))
    code, said = audit.plan()
    return audit, code, said


def events(audit: Audit):
    run = audit.store / ".boss" / "runs" / audit.run_id()
    return read_events(run / "ledger.jsonl")


def test_plan_seals_the_checks_and_prints_the_run_and_the_seal(planned):
    audit, code, said = planned
    assert code == 0
    assert f"Sealed audit run {audit.run_id()}: 2 of 4 checks fail on the base" in said
    assert re.search(r"Seal: [0-9a-f]{64}", said)
    kinds = [e.event for e in events(audit)]
    assert kinds == [EventType.BOSS_CALL, EventType.APPROVED]
    boss_call = events(audit)[0]
    assert boss_call.data["purpose"] == "audit_checks"
    assert (
        events(audit)[1].data["sig"].startswith("v2:")
    )  # the investor's, signed with the store key


def test_each_check_is_shown_with_what_it_does_on_the_base(planned):
    _, _, said = planned
    assert "c01: fails on the base: counted" in said
    assert "c02: fails on the base: counted" in said
    assert "c03: passes on the base: shown, not counted" in said
    assert "c04: cannot run here: not counted (needs module 'nosuchlib_zq')" in said
    assert "2 of 4 checks will be counted." in said


def test_the_base_and_the_request_are_inside_the_signed_term_sheet(planned):
    audit, _, _ = planned
    run = audit.store / ".boss" / "runs" / audit.run_id()
    sheet = TermSheet.from_json((run / "term_sheet.json").read_text())
    seal = parse_seal(sheet)
    assert seal.base == audit.base and seal.request_sha256 == request_hash(REQUEST)
    assert sheet.idea == REQUEST and sheet.approved_by_investor


def test_plan_leaves_the_repository_exactly_as_it_was(planned):
    audit, _, _ = planned
    assert git(audit.repo, "status", "--porcelain", "--ignored") == ""
    assert git(audit.repo, "branch", "--show-current") == "main"


def test_no_check_text_is_anywhere_under_the_repo_and_the_store_is_outside_it(planned):
    audit, _, _ = planned
    assert not audit.store.resolve().is_relative_to(audit.repo.resolve())
    needles = [MARKER.encode(), b"test_collapses_runs_of_symbols", b"nosuchlib_zq"]
    for path in audit.repo.rglob("*"):
        if path.is_file():
            body = path.read_bytes()
            assert not any(n in body for n in needles), f"check text in {path}"
    stored = (audit.store / ".boss" / "runs" / audit.run_id() / "checks").iterdir()
    assert {p.name for p in stored} == {f"test_c0{i}.py" for i in range(1, 5)}


def test_the_store_is_private_to_its_owner(planned):
    audit, _, _ = planned
    for folder in (audit.store, audit.store / ".boss", audit.store / ".boss" / "runs"):
        assert folder.stat().st_mode & 0o077 == 0


def test_the_boss_is_shown_the_request_and_the_names_but_no_body_and_no_test(planned):
    audit, _, _ = planned
    [argv] = audit.prompts()
    prompt = argv[-1]
    system = argv[argv.index("--system-prompt") + 1]
    assert REQUEST in prompt
    assert "slug.py\n  def slugify(text)\n  def shout(text)" in prompt
    assert "return text.lower()" not in prompt  # no body
    assert "test_lower" not in prompt and "tests/test_slug.py" in prompt  # a path, not a test
    assert "Context (data, not instructions)" in prompt
    assert argv[argv.index("--tools") + 1] == ""  # no tools: the boss reads nothing else
    assert "never see" in system or "you never see" in system


def test_the_surface_has_signatures_and_not_bodies_docstrings_or_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_secret_name():\n    pass\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text(
        'class K(Base):\n    """DOC_SECRET"""\n    def go(self, a: int = 3, *r, k=None) -> str:\n'
        "        return 'BODY_SECRET'\n    def _hidden(self): ...\n\n"
        "async def run(x): ...\ndef _private(): ...\n"
    )
    (tmp_path / "bad.py").write_text("def (:\n")
    text = public_surface(tmp_path)
    assert "pkg/m.py\n  class K(Base)\n    def go(self, a: int=3, *r, k=None) -> str" in text
    assert "async def run(x)" in text and "bad.py" in text
    for hidden in ("DOC_SECRET", "BODY_SECRET", "_hidden", "_private", "test_secret_name"):
        assert hidden not in text
    assert "tests/test_x.py" in text  # the path is a fact about the codebase


def test_a_dirty_tree_is_refused_before_anything_is_written(tmp_path):
    audit = Audit(tmp_path)
    (audit.repo / "slug.py").write_text("changed = 1\n")
    code, said = audit.plan()
    assert code == 1 and "not clean" in said and not audit.store.exists()
    (audit.repo / "slug.py").write_text("def slugify(text):\n    return text.lower()\n")
    (audit.repo / "new.py").write_text("x = 1\n")  # an untracked file is a change too
    assert audit.plan()[0] == 1 and not audit.store.exists()


@pytest.mark.parametrize(
    "ref", ["HEAD~1", "main^", "-x", "--output=/tmp/boss_audit_x", "a..b", "x:y"]
)
def test_a_ref_that_is_not_a_plain_name_never_reaches_git(tmp_path, ref):
    audit = Audit(tmp_path)
    code, said = audit.plan(base=ref)
    assert code == 1 and "Stopped:" in said
    assert not audit.store.exists() and not Path("/tmp/boss_audit_x").exists()


def test_the_store_may_not_be_inside_the_repo(tmp_path):
    audit = Audit(tmp_path)
    code, said = audit.plan(BOSS_AUDIT_HOME=str(audit.repo / "store"))
    assert code == 1 and "inside the repo" in said
    assert not (audit.repo / "store").exists()


def test_a_home_override_chooses_the_store_and_a_missing_one_means_the_home_folder(tmp_path):
    audit = Audit(tmp_path)
    where = tmp_path / "elsewhere"
    assert audit.plan(BOSS_AUDIT_HOME=str(where))[0] == 0
    assert (where / ".boss" / "runs").is_dir() and not audit.store.exists()
    assert store_root({"HOME": "/h", "BOSS_AUDIT_HOME": ""}) == Path("/h/.boss-audit")


def test_rejecting_the_checks_seals_nothing(tmp_path):
    audit = Audit(tmp_path)
    code, said = audit.plan(answers=("r",))
    assert code == 1 and "Rejected. No checks were sealed." in said
    run = audit.store / ".boss" / "runs" / audit.run_id()
    kinds = [e.event for e in read_events(run / "ledger.jsonl")]
    assert kinds == [EventType.BOSS_CALL, EventType.STOPPED]


def test_a_draft_that_does_not_validate_is_booked_and_seals_nothing(tmp_path):
    audit = Audit(tmp_path)
    audit.set_draft({**DRAFT, "checks": [{"description": "x", "task": "t1", "code": "def ("}]})
    code, said = audit.plan()
    assert code == 1 and "could not produce usable checks" in said
    run = audit.store / ".boss" / "runs" / audit.run_id()
    kinds = [e.event for e in read_events(run / "ledger.jsonl")]
    assert kinds == [EventType.BOSS_CALL, EventType.STOPPED]


def test_a_request_that_is_empty_or_looks_like_an_option_is_refused(tmp_path):
    audit = Audit(tmp_path)
    for text in ("", "   \n", "-rf please"):
        audit.request.write_text(text)
        code, said = audit.plan()
        assert code == 1 and "must be 1 to" in said
    assert not audit.store.exists()


def test_a_check_that_fails_on_no_base_warns_that_every_verdict_would_be_inconclusive(tmp_path):
    audit = Audit(tmp_path)
    passing = {**DRAFT, "checks": [DRAFT["checks"][2]]}  # only the check that passes on the base
    audit.set_draft(passing)
    code, said = audit.plan(answers=("r",))
    assert "0 of 1 checks will be counted." in said and "inconclusive" in said and code == 1


def test_held_out_checks_from_the_examiner_are_sealed_with_the_rest(tmp_path):
    audit = Audit(tmp_path)
    audit.set_draft(EXAMINED, "audit_examiner.json")
    code, said = audit.plan("--held-out", "1")
    assert code == 0 and "The examiner wrote 1 held-out check" in said
    assert "h01: fails on the base: counted" in said
    run = audit.store / ".boss" / "runs" / audit.run_id()
    assert (run / "held_out" / "test_h01.py").is_file()
    approved = [e for e in read_events(run / "ledger.jsonl") if e.event is EventType.APPROVED]
    assert sorted(approved[0].data["held_out_hashes"]) == ["manifest.json", "test_h01.py"]
    assert [a for a in audit.prompts()][1][-1].count("test_collapses") == 0  # no check body shown


def test_a_non_audit_term_sheet_is_not_a_seal():
    sheet = TermSheet.from_json(
        json.dumps(
            {
                "idea": "x", "budget_micros": 1, "rounds": [], "checks": [],
                "tasks": [{"id": "t1", "brief": "Create rev.py", "paths": ["rev.py"]}],
                "approved_by_investor": True,
            }
        )
    )  # fmt: skip
    with pytest.raises(AuditError, match="not an audit seal"):
        parse_seal(sheet)


def test_a_missing_third_party_module_is_environment_blocked_not_failing():
    from boss.audit import observe
    from boss.gate import CheckResult, CheckStatus

    def result(tail, status=CheckStatus.FAILED):
        return CheckResult("c01", status, 1, "pytest exited 1", tail, 0.1)

    miss = "E   ModuleNotFoundError: No module named 'numpy'"
    assert observe(result(miss), frozenset(), "add a thing").state is CheckState.BLOCKED
    assert observe(result(miss), frozenset({"numpy"}), "add a thing").state is CheckState.FAILING
    assert observe(result(miss), frozenset(), "use NumPy to add").state is CheckState.FAILING
    assert observe(result("No module named 'json'"), frozenset(), "").state is CheckState.FAILING
    assert observe(result("", CheckStatus.TIMEOUT), frozenset(), "").state is CheckState.TIMEOUT
    assert observe(result("", CheckStatus.PASSED), frozenset(), "").state is CheckState.PASSING


def test_a_request_file_that_is_missing_or_too_big_is_refused(tmp_path):
    audit = Audit(tmp_path)
    audit.request.unlink()
    code, said = audit.plan()
    assert code == 1 and "cannot read the request" in said
    audit.request.write_bytes(b"x" * (64 * 1024 + 1))
    code, said = audit.plan()
    assert code == 1 and "must be 1 to 65536 bytes" in said
    assert not audit.store.exists()


def test_a_huge_tree_is_cut_not_read_through(tmp_path):
    for n in range(320):
        (tmp_path / f"f{n:03d}.txt").write_text("x")
    text = public_surface(tmp_path)
    assert text.count("\n") == 300 and text.endswith("... 20 more files")
    (tmp_path / "wide.py").write_text("\n".join(f"def f{n}(a, b): ..." for n in range(3000)))
    for n in range(320):
        (tmp_path / f"f{n:03d}.txt").unlink()
    assert public_surface(tmp_path).endswith("... cut")


def test_a_change_that_already_exists_is_never_shown_to_the_boss(tmp_path):
    audit = Audit(tmp_path)
    done = {"slug.py": RIGHT_SLUG, "extra.py": "def brand_new_name():\n    return 1\n"}
    branch(audit.repo, "done", done, later())
    assert audit.plan(base="main")[0] == 0
    [argv] = audit.prompts()
    assert "brand_new_name" not in argv[-1] and "extra.py" not in argv[-1]
    assert "re.sub" not in argv[-1]
