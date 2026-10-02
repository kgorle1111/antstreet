"""Gate edge cases: environment failures, the verdict rules, and how the workspace is copied."""

import hashlib
import hmac
import importlib.util
import re
from pathlib import Path

import pytest

from boss.gate import OUTPUT_TAIL_CHARS, Check, CheckStatus, GateError, _verdict, run_gate

PASSING = "def test_ok():\n    assert True\n"


@pytest.fixture
def dirs(tmp_path):
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    ws.mkdir()
    checks.mkdir()
    return ws, checks


def write_check(checks: Path, name: str, source: str) -> Check:
    (checks / name).write_text(source)
    return Check(name.removeprefix("test_").removesuffix(".py"), name)


def test_missing_pytest_is_a_gate_error(dirs, monkeypatch):
    ws, checks = dirs
    check = write_check(checks, "test_a.py", PASSING)
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name == "pytest" else real(name, *a)
    )
    with pytest.raises(GateError, match="pytest is not installed"):
        run_gate(ws, checks, [check])


def test_missing_workspace_is_a_gate_error_even_with_no_checks(dirs, tmp_path):
    _, checks = dirs
    with pytest.raises(GateError, match="does not exist"):
        run_gate(tmp_path / "nope", checks, [])


def test_workspace_that_is_a_file_is_a_gate_error(dirs, tmp_path):
    _, checks = dirs
    (tmp_path / "file").write_text("x")
    with pytest.raises(GateError, match="does not exist"):
        run_gate(tmp_path / "file", checks, [])


def test_no_checks_yields_no_results(dirs):
    ws, checks = dirs
    assert run_gate(ws, checks, []) == []


def test_symlinked_check_pointing_outside_the_checks_dir_is_refused(dirs, tmp_path):
    ws, checks = dirs
    outside = tmp_path / "outside.py"
    outside.write_text(PASSING)
    (checks / "test_link.py").symlink_to(outside)
    with pytest.raises(GateError, match="outside the checks directory"):
        run_gate(ws, checks, [Check("link", "test_link.py")])


def test_check_path_that_is_a_directory_is_not_a_file(dirs):
    ws, checks = dirs
    (checks / "test_dir.py").mkdir()
    with pytest.raises(GateError, match="file not found"):
        run_gate(ws, checks, [Check("dir", "test_dir.py")])


def test_one_bad_check_file_stops_the_gate_before_any_check_runs(dirs):
    ws, checks = dirs
    good = write_check(checks, "test_good.py", "def test_ok():\n    open('ran.txt', 'w')\n")
    with pytest.raises(GateError):
        run_gate(ws, checks, [good, Check("gone", "test_gone.py")])
    assert not (ws / "ran.txt").exists()


def test_each_check_gets_a_fresh_workspace_copy(dirs):
    ws, checks = dirs
    first = write_check(
        checks, "test_a_first.py", "def test_ok():\n    open('leak.txt', 'w').write('x')\n"
    )
    second = write_check(
        checks,
        "test_b_second.py",
        "import os\n\ndef test_ok():\n    assert not os.path.exists('leak.txt')\n",
    )
    results = run_gate(ws, checks, [first, second])
    assert [r.check_id for r in results] == ["a_first", "b_second"]
    assert [r.status for r in results] == [CheckStatus.PASSED, CheckStatus.PASSED]


def test_results_keep_the_order_of_the_checks_given(dirs):
    ws, checks = dirs
    bad = write_check(checks, "test_bad.py", "def test_no():\n    assert False\n")
    good = write_check(checks, "test_good.py", PASSING)
    results = run_gate(ws, checks, [bad, good])
    assert [(r.check_id, r.status) for r in results] == [
        ("bad", CheckStatus.FAILED),
        ("good", CheckStatus.PASSED),
    ]
    assert results[0].exit_code == 1
    assert results[0].detail == "pytest exited 1"
    assert results[1].exit_code == 0


def test_git_and_cache_folders_are_not_copied_but_symlinks_are_kept(dirs):
    ws, checks = dirs
    (ws / ".git").mkdir()
    (ws / ".git" / "config").write_text("secret")
    (ws / "__pycache__").mkdir()
    (ws / "stale.pyc").write_bytes(b"\0")
    (ws / "dangling").symlink_to("/nonexistent/target")
    check = write_check(
        checks,
        "test_copy.py",
        "import os\n\n"
        "def test_copy():\n"
        "    assert not os.path.exists('.git')\n"
        "    assert not os.path.exists('__pycache__')\n"
        "    assert not os.path.exists('stale.pyc')\n"
        "    assert os.path.islink('dangling')\n",
    )
    [result] = run_gate(ws, checks, [check])
    assert result.status is CheckStatus.PASSED, result.output_tail


def test_output_tail_is_capped_to_the_last_chars(dirs):
    ws, checks = dirs
    check = write_check(
        checks,
        "test_noisy.py",
        "def test_noisy():\n    print('x' * 20000 + 'THE-END')\n    assert False\n",
    )
    [result] = run_gate(ws, checks, [check])
    assert result.status is CheckStatus.FAILED
    assert len(result.output_tail) == OUTPUT_TAIL_CHARS
    assert "THE-END" in result.output_tail


def test_timeout_reports_the_limit_and_no_exit_code(dirs):
    ws, checks = dirs
    check = write_check(
        checks, "test_hang.py", "import time\n\ndef test_hang():\n    time.sleep(30)\n"
    )
    [result] = run_gate(ws, checks, [check], timeout_s=1.0)
    assert result.status is CheckStatus.TIMEOUT
    assert result.exit_code is None
    assert result.detail == "exceeded 1.0s"
    assert not result.passed


JUNIT_OK = '<testsuite tests="2" failures="0" errors="0" skipped="0"></testsuite>'


NONCE = "ab" * 32
NO_PROOF_DETAIL = "exit 0 but the gate's pytest plugin left no valid proof of a clean session"


def sign(total: object, passed: object = None, nonce: str = NONCE) -> str:
    passed = total if passed is None else passed
    mac = hmac.new(nonce.encode(), f"{total}:{passed}".encode(), hashlib.sha256).hexdigest()
    return f"{total} {passed} {mac}"


def verdict(tmp_path: Path, exit_code, xml: str | None, proof: str | bytes | None = "auto"):
    """`proof="auto"` signs the number of tests the report claims, as an honest run would."""
    report, proof_file = tmp_path / "report.xml", tmp_path / "proof"
    if xml is not None:
        report.write_text(xml)
    if proof == "auto":
        proof = sign(sum(int(n) for n in re.findall(r'<testsuite tests="(\d+)"', xml or "")))
    if isinstance(proof, str):
        proof = proof.encode()
    if proof is not None:
        proof_file.write_bytes(proof)
    return _verdict(exit_code, report, proof_file, NONCE)


@pytest.mark.parametrize(
    ("exit_code", "xml", "expected"),
    [
        (1, JUNIT_OK, (False, "pytest exited 1")),
        (None, JUNIT_OK, (False, "pytest exited None")),
        (0, None, (False, "exit 0 but no JUnit report was written")),
        (0, JUNIT_OK, (True, "2 passed")),
        (0, '<testsuite tests="0"></testsuite>', (False, "no tests ran")),
        (
            0,
            '<testsuite tests="3" failures="1" errors="1" skipped="1"></testsuite>',
            (False, "report shows 1 failed, 1 errors, 1 skipped"),
        ),
        (
            0,
            '<testsuite tests="1" skipped="1"></testsuite>',
            (False, "report shows 0 failed, 0 errors, 1 skipped"),
        ),
        (
            0,
            '<testsuites><testsuite tests="2"></testsuite><testsuite tests="3"></testsuite>'
            "</testsuites>",
            (True, "5 passed"),
        ),
        (
            0,
            '<testsuites><testsuite tests="2"></testsuite>'
            '<testsuite tests="1" failures="1"></testsuite></testsuites>',
            (False, "report shows 1 failed, 0 errors, 0 skipped"),
        ),
        (0, "<testsuites></testsuites>", (False, "no tests ran")),
    ],
)
def test_verdict_rules(tmp_path, exit_code, xml, expected):
    assert verdict(tmp_path, exit_code, xml) == expected


@pytest.mark.parametrize(
    ("proof", "expected"),
    [
        ("auto", (True, "2 passed")),
        (None, (False, NO_PROOF_DETAIL)),
        ("", (False, NO_PROOF_DETAIL)),
        (sign(2, nonce="cd" * 32), (False, NO_PROOF_DETAIL)),  # signed with a nonce we never gave
        (sign(2)[:-1], (False, NO_PROOF_DETAIL)),  # truncated mac
        (sign(2).upper(), (False, NO_PROOF_DETAIL)),
        (sign(2, 1), (False, NO_PROOF_DETAIL)),  # a test that did not pass, though properly signed
        (sign(3), (False, "report shows 2 tests but the proof covers 3")),
        (sign(1), (False, "report shows 2 tests but the proof covers 1")),
        (sign(0), (False, "report shows 2 tests but the proof covers 0")),
        (sign(2) + " extra", (False, NO_PROOF_DETAIL)),
        (sign("two"), (False, NO_PROOF_DETAIL)),
        ("2 2", (False, NO_PROOF_DETAIL)),
        ("2 2 " + "0" * 64, (False, NO_PROOF_DETAIL)),
        (b"\xff\xfe 2 2 zz", (False, NO_PROOF_DETAIL)),
        (b"x" * 100_000, (False, NO_PROOF_DETAIL)),
        (sign(2).encode() + b"\n", (False, NO_PROOF_DETAIL)),  # the plugin writes no newline
    ],
)
def test_a_pass_needs_a_proof_signed_with_this_runs_nonce_and_matching_the_report(
    tmp_path, proof, expected
):
    assert verdict(tmp_path, 0, JUNIT_OK, proof) == expected


def test_a_proof_never_rescues_a_report_or_exit_code_that_says_failed(tmp_path):
    failing = '<testsuite tests="2" failures="1" errors="0" skipped="0"></testsuite>'
    assert verdict(tmp_path, 0, failing, sign(2)) == (
        False,
        "report shows 1 failed, 0 errors, 0 skipped",
    )
    assert verdict(tmp_path, 1, JUNIT_OK, sign(2)) == (False, "pytest exited 1")


def test_a_symlinked_proof_is_not_read(tmp_path):
    real = tmp_path / "real"
    real.write_text(sign(2))
    (tmp_path / "report.xml").write_text(JUNIT_OK)
    link = tmp_path / "proof"
    link.symlink_to(real)
    assert _verdict(0, tmp_path / "report.xml", link, NONCE) == (False, NO_PROOF_DETAIL)


def test_verdict_truncated_report_is_unreadable_not_a_pass(tmp_path):
    ok, detail = verdict(tmp_path, 0, '<testsuite tests="2" failures="0"')
    assert ok is False
    assert detail.startswith("unreadable JUnit report:")
