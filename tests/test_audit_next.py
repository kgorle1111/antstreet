"""`antstreet audit` with no step: it seals checks when no run covers HEAD and checks HEAD when one
does; `--stop-hook` is the same check for the plugin's Stop hook, and never shows a check to
the agent."""

import json
import shutil

import pytest
from audit_support import (
    DRAFT,
    MARKER,
    REQUEST,
    RIGHT_SLUG,
    WRONG_SLUG,
    Audit,
    git,
    later,
    write,
)

from antstreet.cli import STOP_HOOK_AGENT
from antstreet.ledger import audited
from antstreet.rundir import RunPaths


@pytest.fixture(scope="module")
def sealed(tmp_path_factory):
    """One run sealed by `antstreet audit --request`, and two branches past its base."""
    audit = Audit(tmp_path_factory.mktemp("next"))
    code, said = audit.run("--repo", str(audit.repo), "--request", str(audit.request))
    assert code == 0, said
    assert "No sealed audit run covers HEAD" in said and "antstreet audit plan" in said
    assert f"Sealed audit run {audit.run_id()}" in said and "run `antstreet audit` here" in said
    audit.rid = audit.run_id()
    for name, slug in (("bad", WRONG_SLUG), ("good", RIGHT_SLUG)):
        git(audit.repo, "checkout", "-q", "-b", name, "main")
        write(audit.repo, "slug.py", slug)
        git(audit.repo, "commit", "-qam", name, when=later())
    git(audit.repo, "checkout", "-q", "main")
    return audit


@pytest.fixture
def audit(sealed, tmp_path):
    """The sealed repo and store, copied: each test moves HEAD and writes verdicts of its own."""
    copy = Audit.__new__(Audit)
    copy.__dict__ |= sealed.__dict__
    copy.home = tmp_path / "home"
    shutil.copytree(sealed.home, copy.home, symlinks=True)
    copy.repo = tmp_path / "repo"
    shutil.copytree(sealed.repo, copy.repo, symlinks=True)
    return copy


def at(audit: Audit, ref: str) -> None:
    git(audit.repo, "checkout", "-q", ref)


def next_step(audit: Audit, *extra: str) -> tuple[int, str]:
    return audit.run("--repo", str(audit.repo), *extra, answers=())


def hook(audit: Audit, mode: str = "notify") -> tuple[int, str]:
    return audit.run("--repo", str(audit.repo), "--stop-hook", mode, answers=())


def verdicts(audit: Audit):
    return audited(RunPaths(audit.store / ".boss" / "runs" / audit.rid).events())


def test_with_a_run_and_head_unmoved_there_is_nothing_to_check(audit):
    code, said = next_step(audit)
    assert code == 0 and "Nothing to check: HEAD is still the sealed base" in said
    assert verdicts(audit) == []


def test_with_a_run_and_head_moved_it_checks_head_as_done_and_names_the_next_command(audit):
    at(audit, "bad")
    code, said = next_step(audit)
    assert code == 3 and "Verdict: REFUTED (claim: done" in said
    assert f"Next: `antstreet audit report {audit.rid}`" in said
    [event] = verdicts(audit)
    assert event.data["claim"] == "done"
    assert event.data["head"] == git(audit.repo, "rev-parse", "HEAD")


def test_without_a_run_or_a_request_it_says_how_to_give_one_and_seals_nothing(audit):
    shutil.rmtree(audit.store)
    code, said = next_step(audit)
    assert code == 1 and "--request FILE" in said and ".antstreet/request.md" in said
    assert not audit.store.exists()


def test_a_committed_request_file_is_read_and_a_new_request_seals_a_new_run(audit):
    at(audit, "good")
    write(audit.repo, ".antstreet/request.md", REQUEST + " Also keep digits.")
    git(audit.repo, "add", "-A")
    git(audit.repo, "commit", "-qm", "request", when=later())
    code, said = audit.run("--repo", str(audit.repo), answers=("a",))
    assert code == 0 and "for the request in" in said and ".antstreet/request.md" in said
    assert len(list((audit.store / ".boss" / "runs").iterdir())) == 2


def test_the_same_request_again_finds_its_run_instead_of_sealing_another(audit):
    at(audit, "bad")
    code, said = next_step(audit, "--request", str(audit.request))
    assert code == 3 and "Verdict: REFUTED" in said
    assert len(list((audit.store / ".boss" / "runs").iterdir())) == 1


def test_the_stop_hook_is_silent_without_a_run_outside_git_and_on_the_base(audit, tmp_path):
    assert hook(audit) == (0, "")  # HEAD is the base
    shutil.rmtree(audit.store)
    at(audit, "bad")
    assert hook(audit) == (0, "")  # no store
    not_git = tmp_path / "plain"
    not_git.mkdir()
    assert audit.run("--repo", str(not_git), "--stop-hook", "notify") == (0, "")


def test_a_refuted_stop_tells_the_human_and_shows_the_agent_no_check(audit):
    at(audit, "bad")
    write(audit.repo, "scratch.txt", "uncommitted")
    code, said = hook(audit)
    assert code == 0
    out = json.loads(said)
    assert set(out) == {"systemMessage"}  # notify: nothing for the agent, no block
    message = out["systemMessage"]
    assert "REFUTED, 2 of 2 sealed checks failed" in message
    assert "Uncommitted changes in the working tree were not checked" in message
    _assert_no_check_text(said)
    [event] = verdicts(audit)
    assert event.data["agent"] == STOP_HOOK_AGENT and event.data["claim"] == "done"
    assert hook(audit) == (0, "")  # this commit was already checked: said once


def test_block_mode_blocks_a_refuted_stop_with_a_count_only(audit):
    at(audit, "bad")
    code, said = hook(audit, "block")
    out = json.loads(said)
    assert code == 0 and out["decision"] == "block"
    assert out["reason"] == (
        "2 of 2 sealed checks failed; the human has the details (`antstreet audit report`)."
    )
    _assert_no_check_text(said)


def test_block_mode_does_not_block_an_unrefuted_stop(audit):
    at(audit, "good")
    out = json.loads(hook(audit, "block")[1])
    assert set(out) == {"systemMessage"} and "UNREFUTED, 0 of 2" in out["systemMessage"]


def test_a_hook_error_prints_nothing_and_exits_1(audit):
    at(audit, "bad")
    (audit.store / ".boss" / "investor.key").unlink()
    assert hook(audit) == (1, "")


def test_the_stop_hook_flag_is_refused_with_a_step(audit):
    code, said = audit.run("--stop-hook", "notify", "report")
    assert code == 2 and "no step" in said


def _assert_no_check_text(said: str) -> None:
    for check in DRAFT["checks"]:
        assert check["description"] not in said
        assert check["code"] not in said
    for text in (MARKER, "test_collapses_runs_of_symbols", "assert", "c01", "c02"):
        assert text not in said


def test_without_a_request_it_names_the_run_and_the_request_it_checks_against(audit):
    # the newest covering run may have been sealed for another change: the verdict says so
    at(audit, "bad")
    code, said = next_step(audit)
    assert code == 3 and f"No request given, so this checks against run {audit.rid}" in said
    assert REQUEST.strip().splitlines()[0][:60] in said and "--request FILE" in said
    code, said = next_step(audit, "--request", str(audit.request))
    assert "No request given" not in said


def test_the_stop_hook_never_measures_strength(audit, monkeypatch):
    # strength never changes the verdict and can run for minutes; the hook has 60 s
    import antstreet.audit_check as audit_check

    seen = {}
    real = audit_check.check

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(audit_check, "check", spy)
    at(audit, "bad")
    audit.run("--repo", str(audit.repo), "--stop-hook", "notify")
    assert seen.get("strength") is False
