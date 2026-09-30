import hashlib
import os
import time
from pathlib import Path

import pytest

from boss.gate import Check, CheckStatus, GateError, run_gate

CHECK = """
from rev import reverse

def test_reverses_word():
    assert reverse("abc") == "cba"

def test_empty():
    assert reverse("") == ""
"""


@pytest.fixture
def dirs(tmp_path):
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    ws.mkdir()
    checks.mkdir()
    (checks / "test_c01.py").write_text(CHECK)
    return ws, checks


def gate(dirs, timeout_s=30.0):
    ws, checks = dirs
    [result] = run_gate(ws, checks, [Check("c01", "test_c01.py")], timeout_s=timeout_s)
    return result


def product(dirs, source):
    (dirs[0] / "rev.py").write_text(source)


def test_correct_product_passes(dirs):
    product(dirs, "def reverse(s):\n    return s[::-1]\n")
    result = gate(dirs)
    assert result.status is CheckStatus.PASSED, result.output_tail
    assert result.detail == "2 passed"


def test_wrong_product_fails(dirs):
    product(dirs, "def reverse(s):\n    return s\n")
    assert gate(dirs).status is CheckStatus.FAILED


def test_missing_product_fails_rather_than_erroring_the_gate(dirs):
    assert gate(dirs).status is CheckStatus.FAILED


def test_editing_a_copy_of_the_check_inside_the_workspace_changes_nothing(dirs):
    product(dirs, "def reverse(s):\n    return s\n")
    (dirs[0] / "checks").mkdir()
    (dirs[0] / "checks" / "test_c01.py").write_text("def test_ok():\n    assert True\n")
    (dirs[0] / "test_c01.py").write_text("def test_ok():\n    assert True\n")
    assert gate(dirs).status is CheckStatus.FAILED


def test_planted_conftest_cannot_force_a_pass(dirs):
    product(dirs, "def reverse(s):\n    return s\n")
    (dirs[0] / "conftest.py").write_text(
        "import pytest\n"
        "@pytest.hookimpl(tryfirst=True)\n"
        "def pytest_runtest_call(item):\n"
        "    item.runtest = lambda: None\n"
    )
    (dirs[0] / "pytest.ini").write_text("[pytest]\naddopts = --co\n")
    assert gate(dirs).status is CheckStatus.FAILED


def test_shadow_pytest_module_in_workspace_is_not_imported(dirs):
    product(dirs, "def reverse(s):\n    return s\n")
    (dirs[0] / "pytest.py").write_text("import sys\nsys.exit(0)\n")
    (dirs[0] / "sitecustomize.py").write_text("import os\nos._exit(0)\n")
    assert gate(dirs).status is CheckStatus.FAILED


def test_hard_exit_zero_during_import_is_not_a_pass(dirs):
    product(dirs, "import os\nos._exit(0)\n")
    result = gate(dirs)
    assert result.status is CheckStatus.FAILED
    assert "report" in result.detail


def test_abnormal_exit_after_a_passing_report_is_not_a_pass(dirs):
    product(
        dirs,
        "import atexit, os\natexit.register(lambda: os._exit(3))\n"
        "def reverse(s):\n    return s[::-1]\n",
    )
    result = gate(dirs)
    assert result.status is CheckStatus.FAILED
    assert result.detail == "pytest exited 3"


def test_skipped_tests_do_not_count_as_passing(dirs):
    (dirs[1] / "test_c01.py").write_text(
        "import pytest\n@pytest.mark.skip\ndef test_x():\n    pass\n"
    )
    assert gate(dirs).status is CheckStatus.FAILED


def test_hanging_check_times_out_and_its_children_die(dirs, tmp_path):
    pid_file = tmp_path / "child.pid"
    product(
        dirs,
        "import subprocess, sys, time\n"
        f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "time.sleep(60)\n",
    )
    start = time.monotonic()
    result = gate(dirs, timeout_s=2.0)
    assert result.status is CheckStatus.TIMEOUT
    assert time.monotonic() - start < 15
    child = int(pid_file.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)


def test_callers_secrets_do_not_reach_the_check(dirs, monkeypatch):
    monkeypatch.setenv("BOSS_TEST_SECRET", "hunter2")
    product(dirs, "def reverse(s):\n    return s[::-1]\n")
    (dirs[1] / "test_c01.py").write_text(
        "import os\ndef test_env():\n    assert 'BOSS_TEST_SECRET' not in os.environ\n"
    )
    assert gate(dirs).status is CheckStatus.PASSED


def test_original_workspace_is_never_modified(dirs):
    product(dirs, "def reverse(s):\n    return s[::-1]\n")

    def digest(root: Path) -> str:
        h = hashlib.sha256()
        for p in sorted(root.rglob("*")):
            h.update(str(p.relative_to(root)).encode())
            if p.is_file():
                h.update(p.read_bytes())
        return h.hexdigest()

    before = digest(dirs[0])
    gate(dirs)
    assert digest(dirs[0]) == before


def test_check_paths_cannot_escape_the_checks_directory(dirs):
    with pytest.raises(GateError, match="outside"):
        run_gate(dirs[0], dirs[1], [Check("c01", "../ws/rev.py")])


def test_missing_check_file_is_a_gate_error_not_a_worker_failure(dirs):
    with pytest.raises(GateError, match="not found"):
        run_gate(dirs[0], dirs[1], [Check("c02", "test_c02.py")])
