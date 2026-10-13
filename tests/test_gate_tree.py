"""`run_tree`: a whole pytest tree against a copy of a product, every test reported by node id."""

import pytest

from antstreet.gate import CheckStatus, GateError, run_tree

PASSED, FAILED, TIMEOUT = CheckStatus.PASSED, CheckStatus.FAILED, CheckStatus.TIMEOUT
SUITE = """import pytest

class TestK:
    def test_m(self):
        pass

    @pytest.mark.parametrize("v", ["a b", 1])
    def test_p(self, v):
        assert v != 1

def test_fails():
    assert 0

def test_skips():
    pytest.skip("not today")

@pytest.mark.xfail
def test_xfails():
    assert 0
"""


@pytest.fixture
def dirs(tmp_path):
    ws, tree = tmp_path / "ws", tmp_path / "tree"
    (tree / "sub").mkdir(parents=True)
    ws.mkdir()
    (tree / "__init__.py").write_text("")
    (tree / "sub" / "__init__.py").write_text("")
    return ws, tree


def test_node_ids_are_files_classes_and_parameters_and_only_passes_pass(dirs):
    ws, tree = dirs
    (tree / "test_a.py").write_text(SUITE)
    (tree / "sub" / "test_b.py").write_text("def test_ok():\n    pass\n")
    got = run_tree(ws, tree, "tests")
    assert got.tests == {
        "tests/test_a.py::TestK::test_m": PASSED,
        "tests/test_a.py::TestK::test_p[a b]": PASSED,
        "tests/test_a.py::TestK::test_p[1]": FAILED,
        "tests/test_a.py::test_fails": FAILED,
        "tests/test_a.py::test_skips": FAILED,  # a skip is not a pass
        "tests/test_a.py::test_xfails": FAILED,
        "tests/sub/test_b.py::test_ok": PASSED,
    }
    assert got.sandboxed in (True, False) and got.detail == "3 of 7 passed"


def test_a_collection_error_is_one_failed_entry_and_the_rest_still_run(dirs):
    ws, tree = dirs
    (tree / "test_bad.py").write_text("import nothing_here_at_all\n\ndef test_x():\n    pass\n")
    (tree / "test_good.py").write_text("def test_y():\n    pass\n")
    got = run_tree(ws, tree, "tests")
    assert got.tests == {"tests/test_bad.py": FAILED, "tests/test_good.py::test_y": PASSED}
    assert got.missing_modules == ("nothing_here_at_all",)


def test_the_product_is_importable_and_its_own_test_folder_is_replaced(dirs):
    ws, tree = dirs
    (ws / "lib.py").write_text("VALUE = 3\n")
    (ws / "tests").mkdir()
    (ws / "tests" / "test_own.py").write_text("def test_own():\n    pass\n")
    (tree / "test_lib.py").write_text("import lib\n\ndef test_v():\n    assert lib.VALUE == 3\n")
    assert run_tree(ws, tree, "tests").tests == {"tests/test_lib.py::test_v": PASSED}
    assert (ws / "tests" / "test_own.py").is_file()  # the original is never modified


def test_a_product_that_made_its_test_path_a_symlink_or_a_file_is_replaced_too(dirs, tmp_path):
    ws, tree = dirs
    (tree / "test_a.py").write_text("def test_a():\n    pass\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (ws / "tests").symlink_to(elsewhere)
    assert run_tree(ws, tree, "tests").tests == {"tests/test_a.py::test_a": PASSED}
    assert list(elsewhere.iterdir()) == []  # nothing was written through the link
    (ws / "tests").unlink()
    (ws / "tests").write_text("not a folder")
    assert run_tree(ws, tree, "tests").tests == {"tests/test_a.py::test_a": PASSED}


def test_support_files_are_laid_over_the_product_root(dirs, tmp_path):
    ws, tree = dirs
    support = tmp_path / "support"
    support.mkdir()
    (support / "shim.py").write_text("ANSWER = 42\n")
    (ws / "shim.py").write_text("ANSWER = 0\n")
    (tree / "test_s.py").write_text("import shim\n\ndef test_s():\n    assert shim.ANSWER == 42\n")
    assert run_tree(ws, tree, "tests", support=support).tests == {"tests/test_s.py::test_s": PASSED}
    assert run_tree(ws, tree, "tests").tests == {"tests/test_s.py::test_s": FAILED}


def test_a_nested_test_path_works(dirs):
    ws, tree = dirs
    (tree / "test_a.py").write_text("def test_a():\n    pass\n")
    assert run_tree(ws, tree, "pkg/tests").tests == {"pkg/tests/test_a.py::test_a": PASSED}


def test_a_hang_past_the_suite_cap_is_a_timeout_of_the_running_test(dirs):
    ws, tree = dirs
    (tree / "test_h.py").write_text("import time\n\ndef test_h():\n    time.sleep(60)\n")
    got = run_tree(ws, tree, "tests", timeout_s=2.0, test_timeout_s=50.0)
    assert got.tests == {"tests/test_h.py::test_h": TIMEOUT} and got.timed_out
    assert got.exit_code is None and "exceeded 2.0s" in got.detail


def test_a_crash_with_no_report_is_no_results_not_an_exception(dirs):
    ws, tree = dirs
    (tree / "test_k.py").write_text("import os\n\ndef test_k():\n    os._exit(3)\n")
    got = run_tree(ws, tree, "tests")
    assert got.tests == {} and "no readable JUnit report" in got.detail


@pytest.mark.parametrize("path", ["", ".", "..", "../x", "a/../../x", "/abs"])
def test_a_test_path_outside_the_product_is_refused(dirs, path):
    ws, tree = dirs
    with pytest.raises(GateError, match="relative path inside the product"):
        run_tree(ws, tree, path)


def test_a_missing_folder_is_a_gate_error(dirs, tmp_path):
    ws, tree = dirs
    with pytest.raises(GateError, match="does not exist"):
        run_tree(tmp_path / "nope", tree, "tests")
    with pytest.raises(GateError, match="does not exist"):
        run_tree(ws, tmp_path / "nope", "tests")


def test_a_src_layout_product_is_importable_when_the_caller_names_the_folder(dirs):
    ws, tree = dirs
    (ws / "src" / "lib").mkdir(parents=True)
    (ws / "src" / "lib" / "__init__.py").write_text("VALUE = 3\n")
    (tree / "test_lib.py").write_text("import lib\n\ndef test_v():\n    assert lib.VALUE == 3\n")
    assert run_tree(ws, tree, "tests").tests == {"tests/test_lib.py": FAILED}  # not importable
    got = run_tree(ws, tree, "tests", pythonpath=("ws", "ws/src"))
    assert got.tests == {"tests/test_lib.py::test_v": PASSED}
    with pytest.raises(GateError, match="not inside the workspace copy"):
        run_tree(ws, tree, "tests", pythonpath=("ws/../..",))


# --- time limits -------------------------------------------------------------------------------

HANGS = """import time

def test_before():
    pass

def test_sleeps_forever():
    while True:
        time.sleep(0.05)

def test_spins_forever():
    while True:
        pass

def test_swallows_exceptions():
    while True:
        try:
            time.sleep(0.05)
        except Exception:
            pass

def test_slow_but_inside_the_limit():
    time.sleep(0.3)

def test_after():
    pass
"""


def test_one_hanging_test_is_a_timeout_and_the_others_still_report(dirs):
    ws, tree = dirs
    (tree / "test_h.py").write_text(HANGS)
    got = run_tree(ws, tree, "tests", test_timeout_s=1.0)
    assert got.tests == {
        "tests/test_h.py::test_before": PASSED,
        "tests/test_h.py::test_sleeps_forever": TIMEOUT,
        "tests/test_h.py::test_spins_forever": TIMEOUT,  # pure Python, no sleep to interrupt
        "tests/test_h.py::test_swallows_exceptions": TIMEOUT,  # `except Exception` cannot eat it
        "tests/test_h.py::test_slow_but_inside_the_limit": PASSED,
        "tests/test_h.py::test_after": PASSED,
    }
    assert got.detail == "3 of 6 passed (3 timed out)" and not got.timed_out
    assert got.duration_s < 20  # three limits of 1 s each plus start-up, not the 180 s suite cap


def test_a_timed_out_test_is_not_a_failed_one_and_a_failed_one_is_not_a_timeout(dirs):
    ws, tree = dirs
    (tree / "test_m.py").write_text(
        "import time\n\ndef test_wrong():\n    assert 0\n\ndef test_hangs():\n    time.sleep(30)\n"
    )
    got = run_tree(ws, tree, "tests", test_timeout_s=1.0)
    assert got.tests["tests/test_m.py::test_wrong"] is FAILED
    assert got.tests["tests/test_m.py::test_hangs"] is TIMEOUT


def test_a_hang_in_a_fixture_is_a_timeout_of_that_test_alone(dirs):
    ws, tree = dirs
    (tree / "test_f.py").write_text(
        "import time, pytest\n\n@pytest.fixture\ndef slow():\n    time.sleep(30)\n\n"
        "def test_needs_it(slow):\n    pass\n\ndef test_free():\n    pass\n"
    )
    got = run_tree(ws, tree, "tests", test_timeout_s=1.0)
    assert got.tests == {
        "tests/test_f.py::test_needs_it": TIMEOUT,
        "tests/test_f.py::test_free": PASSED,
    }


def test_a_test_that_disables_the_alarm_is_cut_by_the_suite_cap_and_keeps_what_finished(dirs):
    ws, tree = dirs
    (tree / "test_s.py").write_text(
        "import signal, time\n\ndef test_first():\n    pass\n\n"
        "def test_deaf():\n    signal.setitimer(signal.ITIMER_REAL, 0)\n    time.sleep(60)\n\n"
        "def test_never_starts():\n    pass\n"
    )
    got = run_tree(ws, tree, "tests", timeout_s=4.0, test_timeout_s=1.0)
    assert got.timed_out and got.exit_code is None
    assert got.tests == {
        "tests/test_s.py::test_first": PASSED,
        "tests/test_s.py::test_deaf": TIMEOUT,
    }
    assert got.detail == "suite exceeded 4.0s with 1 test(s) running or unfinished"


def test_the_suite_cap_still_works_with_no_progress_at_all(dirs):
    ws, tree = dirs
    (tree / "test_c.py").write_text("import time\ntime.sleep(60)\n\ndef test_x():\n    pass\n")
    got = run_tree(ws, tree, "tests", timeout_s=3.0)
    assert got.timed_out and got.tests == {}  # it hung while being collected


@pytest.mark.parametrize("bad", [0, -1.0, float("inf"), float("nan")])
def test_nonsense_limits_are_refused(dirs, bad):
    ws, tree = dirs
    (tree / "test_a.py").write_text("def test_a():\n    pass\n")
    for name in ("timeout_s", "test_timeout_s"):
        with pytest.raises(GateError, match=name):
            run_tree(ws, tree, "tests", **{name: bad})
