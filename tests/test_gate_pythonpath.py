"""`run_gate(pythonpath=...)`: src-layout products import; the default is what it always was."""

import pytest

from antstreet.gate import Check, CheckStatus, GateError, _ini, run_gate

CHECK = "from rev import reverse\n\ndef test_it():\n    assert reverse('ab') == 'ba'\n"


@pytest.fixture
def src_layout(tmp_path):
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    (ws / "src").mkdir(parents=True)
    checks.mkdir()
    (ws / "src" / "rev.py").write_text("def reverse(s):\n    return s[::-1]\n")
    (checks / "test_c01.py").write_text(CHECK)
    return ws, checks


def gate(dirs, **kwargs):
    [result] = run_gate(*dirs, [Check("c01", "test_c01.py")], timeout_s=30.0, **kwargs)
    return result


def test_the_default_ini_is_byte_for_byte_what_it_was():
    assert _ini(("ws",)) == "[pytest]\npythonpath = ws\n"


def test_a_src_layout_product_does_not_import_by_default(src_layout):
    assert gate(src_layout).status is CheckStatus.FAILED


def test_a_src_layout_product_imports_when_its_src_folder_is_on_the_path(src_layout):
    result = gate(src_layout, pythonpath=("ws", "ws/src"))
    assert result.status is CheckStatus.PASSED, result.output_tail


@pytest.mark.parametrize(
    "entry",
    ["/etc", "ws/../..", "..", "other", "ws\n[pytest]", "ws/a b", "ws/a,b", "", "~", "src"],
)
def test_an_entry_outside_the_copy_or_with_a_separator_is_refused(src_layout, entry):
    with pytest.raises(GateError, match="pythonpath"):
        gate(src_layout, pythonpath=(entry,))


@pytest.mark.parametrize("bad", ["ws", ()])
def test_the_path_must_be_a_non_empty_list_not_a_string(src_layout, bad):
    with pytest.raises(GateError, match="non-empty list"):
        gate(src_layout, pythonpath=bad)
