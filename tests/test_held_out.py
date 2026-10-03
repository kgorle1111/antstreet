"""The held-out store (`boss.held_out`) and how approval binds to it: files, manifest, the gate the
folder must pass, the investor's review of it, and the approval that goes void when it changes."""

import json

import pytest

from boss import held_out
from boss.approval import (
    NotApprovedError,
    content_hashes,
    render,
    require_approval,
    review_term_sheet,
)
from boss.held_out import HeldOutCheck, HeldOutError
from boss.ledger import Event, EventType, LedgerWriter, read_events
from boss.rundir import RunPaths
from boss.termsheet import CheckSpec, Round, Task, TermSheet

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
H01 = "from rev import reverse\n\ndef test_empty():\n    assert reverse('') == ''\n"
H02 = "import rev\n\ndef test_type():\n    assert rev.reverse('abc') == 'cba'\n"
SHEET = TermSheet(
    idea="Reverse a string. reverse('') returns ''.",
    budget_micros=500_000,
    rounds=(Round(1, 500_000, 1),),
    checks=(CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
    tasks=(Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
)


def entry(check_id, code, source="reverse('') returns ''"):
    return HeldOutCheck(check_id, held_out.file_name(check_id), source), code


@pytest.fixture
def run(tmp_path):
    paths = RunPaths(tmp_path)
    paths.checks.mkdir()
    (paths.checks / "test_c01.py").write_text(C01)
    held_out.write(paths.held_out, [entry("h01", H01), entry("h02", H02)])
    return paths


def review(paths, answers, edits=None):
    calls, said = [], []

    def ask(prompt):
        index = len(calls)
        calls.append(prompt)
        if edits and index in edits:
            edits[index]()
        return answers[index]

    with LedgerWriter(paths.ledger) as ledger:
        result = review_term_sheet(
            SHEET, paths.checks, paths.root, ledger, "r1",
            ask=ask, say=said.append, held_out_dir=paths.held_out,
        )  # fmt: skip
    return result, said, read_events(paths.ledger)


# --- the folder: write, load, hash -------------------------------------------------------------


def test_what_is_written_loads_back_and_the_folder_is_hashed_file_by_file(run):
    assert held_out.load(run.held_out) == [
        HeldOutCheck("h01", "test_h01.py", "reverse('') returns ''"),
        HeldOutCheck("h02", "test_h02.py", "reverse('') returns ''"),
    ]
    assert set(held_out.hashes(run.held_out)) == {"manifest.json", "test_h01.py", "test_h02.py"}


def test_no_folder_means_no_checks_and_no_hashes(tmp_path):
    assert held_out.load(tmp_path / "held_out") == []
    assert held_out.hashes(tmp_path / "held_out") == {}
    assert held_out.problems(tmp_path / "held_out") == []


@pytest.mark.parametrize(
    "text",
    ["", "not json", "[]", '{"checks": 3}', '{"checks": [{"id": "h01"}]}', '{"checks": [3]}'],
)
def test_a_manifest_that_is_not_one_is_a_named_error_and_a_problem(tmp_path, text):
    (tmp_path / held_out.MANIFEST).write_text(text)
    with pytest.raises(HeldOutError, match="not a held-out manifest"):
        held_out.load(tmp_path)
    assert held_out.problems(tmp_path)[0].startswith("manifest.json is not a held-out manifest")


# --- the gate the folder must pass (shared by the examiner and the investor's edits) -----------


def test_a_good_folder_passes_the_gate(run):
    assert held_out.problems(run.held_out, {"c01"}) == []


def test_ids_must_look_like_h01_be_unique_and_not_a_visible_checks(tmp_path):
    found = held_out.id_problems(["h01", "h01", "x1", "c01"], {"c01"})
    assert "duplicate held-out check id 'h01'" in found
    assert "held-out check id 'x1' must look like h01" in found
    assert "held-out check id 'c01' must look like h01" in found
    assert "held-out check id 'c01' is also a visible check's id" in found
    assert held_out.id_problems(["h01", "h02"], {"c01"}) == []


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("def test_x(:\n", "syntax error"),
        ("from rev import reverse\n", "defines no test_ function"),
    ],
)
def test_a_file_that_does_not_parse_or_has_no_test_is_a_problem(tmp_path, code, message):
    held_out.write(tmp_path, [entry("h01", code)])
    assert any(message in p for p in held_out.problems(tmp_path))


def test_a_check_that_passes_on_an_empty_workspace_is_a_problem(tmp_path):
    held_out.write(tmp_path, [entry("h01", "def test_x():\n    assert True\n")])
    assert held_out.problems(tmp_path) == ["check h01 passes on an empty workspace"]


def test_a_file_the_manifest_does_not_list_is_a_problem(run):
    (run.held_out / "test_h09.py").write_text(H01)
    assert "test_h09.py is in the folder but not in the manifest" in held_out.problems(run.held_out)


def test_a_folder_with_files_and_no_manifest_is_a_problem(tmp_path):
    (tmp_path / "test_h01.py").write_text(H01)
    assert held_out.problems(tmp_path) == ["no held-out checks are listed"]


def test_a_manifest_file_name_other_than_the_ids_is_refused_without_reading_it(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"checks": [{"id": "h01", "file": "../x.py", "source": "s"}]})
    )
    assert held_out.problems(tmp_path) == ["held-out check h01 file must be test_h01.py"]


# --- approval binds to the folder --------------------------------------------------------------


def test_approval_records_the_held_out_hashes_beside_the_term_sheets(run):
    approved, _, events = review(run, ["a"])
    [event] = events
    assert event.data["held_out_hashes"] == held_out.hashes(run.held_out)
    assert event.data["hashes"] == content_hashes(approved, run.checks)
    require_approval(events, approved, run.checks, run.held_out)


def test_a_run_without_held_out_checks_records_no_key_and_nothing_changes(tmp_path):
    paths = RunPaths(tmp_path)
    paths.checks.mkdir()
    (paths.checks / "test_c01.py").write_text(C01)
    _, _, [event] = review(paths, ["a"])
    assert set(event.data) == {"hashes"}
    require_approval([event], SHEET, paths.checks, paths.held_out)
    require_approval([event], SHEET, paths.checks)


@pytest.mark.parametrize("change", ["edit", "delete", "add", "manifest"])
def test_changing_the_held_out_folder_after_approval_voids_it(run, change):
    approved, _, events = review(run, ["a"])
    if change == "edit":
        (run.held_out / "test_h01.py").write_text(H01 + "\n")
    elif change == "delete":
        (run.held_out / "test_h02.py").unlink()
    elif change == "add":
        (run.held_out / "test_h03.py").write_text(H02)
    else:
        (run.held_out / "manifest.json").write_text('{"checks": []}')
    with pytest.raises(NotApprovedError):
        require_approval(events, approved, run.checks, run.held_out)


def test_a_folder_that_appears_after_an_approval_without_one_voids_it(tmp_path):
    paths = RunPaths(tmp_path)
    paths.checks.mkdir()
    (paths.checks / "test_c01.py").write_text(C01)
    approved, _, events = review(paths, ["a"])
    held_out.write(paths.held_out, [entry("h01", H01)])
    with pytest.raises(NotApprovedError):
        require_approval(events, approved, paths.checks, paths.held_out)


def test_an_approval_that_names_other_hashes_does_not_match(run):
    approved, _, [event] = review(run, ["a"])
    forged = Event(
        run="r1", round=0, actor="investor", event=EventType.APPROVED,
        data=event.data | {"held_out_hashes": {"test_h01.py": "0" * 64}},
    )  # fmt: skip
    with pytest.raises(NotApprovedError):
        require_approval([forged], approved, run.checks, run.held_out)


# --- the investor reads them, and an edit cannot slip past the gate ----------------------------


def test_the_investor_is_shown_each_held_out_check_in_full_marked_as_unseen_by_workers(run):
    _, said, _ = review(run, ["r"])
    shown = "\n".join(said)
    assert "HELD-OUT CHECKS" in shown and "workers never see them" in shown
    assert "Held-out check h01 verifies: reverse('') returns ''" in shown
    assert H01.strip() in shown and H02.strip() in shown
    assert str(run.held_out / "test_h02.py") in shown


def test_a_run_without_held_out_checks_shows_no_such_section(tmp_path):
    paths = RunPaths(tmp_path)
    paths.checks.mkdir()
    (paths.checks / "test_c01.py").write_text(C01)
    assert "HELD-OUT" not in render(SHEET, paths.checks, paths.held_out)
    assert render(SHEET, paths.checks) == render(SHEET, paths.checks, paths.held_out)


def test_an_unreadable_manifest_is_shown_as_such_rather_than_raising(run):
    (run.held_out / "manifest.json").write_text("{")
    assert "HELD-OUT CHECKS cannot be shown" in render(SHEET, run.checks, run.held_out)


def test_an_edit_that_breaks_a_held_out_check_is_refused_until_fixed(run):
    def break_check():
        (run.held_out / "test_h01.py").write_text("def test_x():\n    assert True\n")

    def fix_check():
        (run.held_out / "test_h01.py").write_text(H01)

    approved, said, [event] = review(run, ["e", "", "", "a"], edits={1: break_check, 2: fix_check})
    assert any("check h01 passes on an empty workspace" in s for s in said if s)
    assert approved is not None
    assert any(f"and {run.held_out}" in s for s in said)  # the edit prompt names the folder
    assert event.data["held_out_hashes"] == held_out.hashes(run.held_out)


def test_a_held_out_file_edited_after_it_was_shown_is_not_approved_unseen(run):
    def edit():
        (run.held_out / "test_h02.py").write_text(H02 + "\n# edited\n")

    approved, said, events = review(run, ["a", "a"], edits={0: edit})
    assert "The term sheet or a check changed since it was shown; review it again." in said
    assert approved is not None
    [event] = events
    assert event.data["held_out_hashes"] == held_out.hashes(run.held_out)
    assert "# edited" in (run.held_out / "test_h02.py").read_text()
