"""`run_tree`: a whole pytest tree against a copy of a product, every test reported by node id."""

import pytest

from boss.gate import CheckStatus, GateError, run_tree

PASSED, FAILED = CheckStatus.PASSED, CheckStatus.FAILED
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


def test_a_hang_is_a_timeout_with_no_results(dirs):
    ws, tree = dirs
    (tree / "test_h.py").write_text("import time\n\ndef test_h():\n    time.sleep(60)\n")
    got = run_tree(ws, tree, "tests", timeout_s=2.0)
    assert got.tests == {} and got.exit_code is None and "exceeded 2.0s" in got.detail


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
