"""Tests added after mutation-checking boss.handoff: each one fails on a specific single-line
mutant that tests/test_handoff.py let through (the mutant is named in each docstring)."""

import os
from pathlib import Path

import pytest

from boss.errors import Outcome
from boss.gate import CheckResult, CheckStatus
from boss.handoff import PREVIOUS_DIR, failure_notes, prepare_workspace
from boss.rule import Decision, SliceRecord, Verdict

VERDICT = Verdict(Decision.FIRE, "no new passing check in 2 slices")
HISTORY = [SliceRecord(1, 1000, Outcome.COMPLETED, "continuing", frozenset())]
MARKER = "[notes truncated]"


def _result(check_id: str, status: CheckStatus, detail: str = "", tail: str = "") -> CheckResult:
    return CheckResult(check_id, status, 1, detail, tail, 0.1)


def _failing(tail: str = "") -> list[CheckResult]:
    return [_result("x", CheckStatus.FAILED, "d", tail)]


def test_a_secret_straddling_the_500_char_cut_of_the_last_note_is_fully_masked() -> None:
    """Mutants: no redact on the last note; cut the last note to 500 chars before redacting it.
    The whole-text redact afterwards cannot save a secret that was already cut in half."""
    secret = "sk-ant-api03-" + "q" * 30
    notes = failure_notes(VERDICT, HISTORY, _failing(), "n" * 489 + " " + secret)
    assert "sk-ant" not in notes
    assert notes.endswith("n" * 489 + " [REDACTED]")


def test_truncation_keeps_exactly_max_chars_of_the_head_before_the_marker() -> None:
    """Mutant: cut one character more than needed (result one char under max_chars)."""
    results = _failing("\n".join(f"row {i}" for i in range(500)))
    full = failure_notes(VERDICT, HISTORY, results, None, max_chars=10**6, tail_chars=4000)
    cut = failure_notes(VERDICT, HISTORY, results, None, max_chars=300, tail_chars=4000)
    assert len(cut) == 300
    assert cut == full[: 300 - len(MARKER) - 1] + "\n" + MARKER


def test_smallest_allowed_max_chars_is_marker_length_plus_one() -> None:
    """Mutant: the lower-bound guard is off by one."""
    with pytest.raises(ValueError):
        failure_notes(VERDICT, HISTORY, _failing(), None, max_chars=len(MARKER))
    only_marker = failure_notes(VERDICT, HISTORY, _failing(), None, max_chars=len(MARKER) + 1)
    assert only_marker == "\n" + MARKER


def test_tail_chars_zero_drops_the_output_tails() -> None:
    """Mutant: without the guard, `text[-0:]` is the whole text, so 0 would mean 'everything'."""
    notes = failure_notes(VERDICT, HISTORY, _failing("OUTPUT-BODY"), None, tail_chars=0)
    assert "OUTPUT-BODY" not in notes
    assert notes.endswith("Check x: failed (d)")


def test_a_whitespace_only_tail_adds_no_line() -> None:
    """Mutant: `if tail` instead of `if tail.strip()` emits a stray whitespace line."""
    blank = failure_notes(VERDICT, HISTORY, _failing("   \n\n"), None)
    assert blank == failure_notes(VERDICT, HISTORY, _failing(""), None)


def test_passing_checks_are_listed_in_sorted_order_whatever_the_gate_order() -> None:
    """Mutant: the passing list keeps gate order."""
    results = [_result(c, CheckStatus.PASSED) for c in ("z_last", "a_first", "m_mid")]
    notes = failure_notes(VERDICT, HISTORY, results, None)
    assert notes.splitlines()[1] == "Checks passing when it stopped: a_first, m_mid, z_last"


def _touch(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_prepare_workspace_returns_paths_sorted_across_directories(tmp_path: Path) -> None:
    """Mutant: return in walk order (a directory's own files come before its subdirectories, so
    'b.py' would precede 'a/x.py')."""
    prev = tmp_path / "prev"
    _touch(prev / "b.py")
    _touch(prev / "a" / "x.py")
    assert prepare_workspace(prev, tmp_path / "new") == ["a/x.py", "b.py"]


def test_prepare_workspace_keeps_the_executable_bit(tmp_path: Path) -> None:
    """Mutant: shutil.copyfile instead of copy2 drops the file mode."""
    prev = tmp_path / "prev"
    script = prev / "run.sh"
    _touch(script, "#!/bin/sh\n")
    os.chmod(script, 0o755)
    new = tmp_path / "new"
    prepare_workspace(prev, new)
    assert (new / PREVIOUS_DIR / "run.sh").stat().st_mode & 0o777 == 0o755
