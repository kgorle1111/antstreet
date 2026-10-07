"""B19: a check cannot forge its own verdict. Product code that exits 0, rewrites the report,
patches pytest or writes the proof must be FAILED, sandboxed or not, and honest checks must pass.

What is not stopped (code that reads the nonce out of its own process) is pinned by
`tests/test_safety.py::test_accepted_risk_code_aimed_at_the_gate_can_forge_a_pass`.
"""

from pathlib import Path

import gate_forgers as forge
import pytest

from boss.gate import Check, CheckResult, CheckStatus, run_gate
from boss.sandbox import SandboxMode, detect

FIXTURE = "import pytest\n@pytest.fixture\ndef boom():\n"
NO_PROOF = "exit 0 but the gate's pytest plugin left no valid proof of a clean session"
MODES = [
    pytest.param(SandboxMode.OFF, id="unsandboxed"),
    pytest.param(
        SandboxMode.REQUIRE,
        id="sandboxed",
        marks=pytest.mark.skipif(detect() is None, reason="no working OS sandbox on this machine"),
    ),
]
TWO_TESTS = """\
from rev import reverse

def test_a():
    assert reverse('ab') == 'ba'

def test_b():
    assert reverse('') == ''
"""


@pytest.fixture(params=MODES)
def mode(request) -> SandboxMode:
    return request.param


def gate(tmp_path: Path, product: str, mode: SandboxMode, check: str = forge.CHECK) -> CheckResult:
    ws, checks = tmp_path / "ws", tmp_path / "checks"
    ws.mkdir(parents=True, exist_ok=True)
    checks.mkdir(exist_ok=True)
    (ws / "rev.py").write_text(product)
    (checks / "test_c01.py").write_text(check)
    [result] = run_gate(ws, checks, [Check("c01", "test_c01.py")], timeout_s=60, sandbox=mode)
    assert result.sandboxed is (mode is not SandboxMode.OFF)
    return result


# --- every forgery is FAILED -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("attack", "detail"),
    [
        (forge.REPORT_FORGER, NO_PROOF),  # a clean JUnit file and exit 0, nothing else
        (forge.EXIT_AT_IMPORT, "exit 0 but no JUnit report was written"),
        (forge.SYS_EXIT_AT_IMPORT, "pytest exited 3"),
        (forge.EXIT_ZERO_AT_EXIT, "report shows 1 failed, 0 errors, 0 skipped"),
        (
            forge.PATCHED_REPORT,
            NO_PROOF,
        ),  # pytest itself, the report and the exit code all say pass
        (forge.HOOKED_REPORT, NO_PROOF),
        (forge.SWALLOWED_FAILURE, NO_PROOF),
        (forge.PREEMPTED_CALL, NO_PROOF),
        (forge.NOOP_RUNTEST, NO_PROOF),
        (forge.DESELECT_ALL, "pytest exited 5"),
        (forge.PROOF_GUESSER, NO_PROOF),  # knows where the proof goes, not how it is signed
    ],
    ids=[
        "rewritten-report",
        "exit-at-import",
        "sys-exit-at-import",
        "exit-zero-at-exit",
        "patched-report",
        "hooked-report",
        "swallowed-failure",
        "preempted-call",
        "noop-runtest",
        "deselect-all",
        "guessed-proof",
    ],
)
def test_a_product_aimed_at_the_gate_is_failed(tmp_path, mode, attack, detail):
    result = gate(tmp_path, attack + forge.WRONG, mode)
    assert result.status is CheckStatus.FAILED
    assert result.detail == detail


def test_dropping_one_of_two_tests_after_collection_is_failed(tmp_path, mode):
    # exit 0 and a report of one passing test: only the plugin knows two were collected.
    dropper = forge.DESELECT_ALL.replace("items.clear()", "items.pop()")
    result = gate(tmp_path, dropper + forge.RIGHT, mode, check=TWO_TESTS)
    assert result.status is CheckStatus.FAILED
    assert result.detail == NO_PROOF


@pytest.mark.parametrize(
    "attack",
    [forge.PATCHED_REPORT, forge.HOOKED_REPORT, forge.SWALLOWED_FAILURE, forge.PREEMPTED_CALL],
)
def test_patching_pytests_outcome_hides_a_real_failure_from_everything_but_the_proof(
    tmp_path, attack
):
    result = gate(tmp_path, attack + forge.WRONG, SandboxMode.OFF)
    assert result.exit_code == 0  # the process, its report and the exit code were all fooled
    assert "1 passed" in result.output_tail
    assert result.status is CheckStatus.FAILED


def test_patched_reports_cannot_hide_a_failing_teardown(tmp_path, mode):
    check = (
        "import rev\n"
        + FIXTURE
        + "    yield\n    raise RuntimeError\ndef test_x(boom):\n    pass\n"
    )
    result = gate(tmp_path, forge.PATCHED_REPORT + forge.RIGHT, mode, check=check)
    assert result.status is CheckStatus.FAILED and result.detail == NO_PROOF


def test_a_patched_report_cannot_hide_one_failing_test_among_two(tmp_path, mode):
    half_right = "def reverse(s):\n    return s[::-1] if s else 'x'\n"
    result = gate(tmp_path, forge.PATCHED_REPORT + half_right, mode, check=TWO_TESTS)
    assert result.status is CheckStatus.FAILED and result.detail == NO_PROOF


def test_the_plugin_file_is_gone_before_any_worker_code_runs(tmp_path, mode):
    gone = forge.FIND_PLUGIN + "import os\nassert not os.path.exists(_plugin().__file__)\n"
    assert gate(tmp_path, gone + forge.RIGHT, mode).status is CheckStatus.PASSED


def test_squatting_on_the_proof_file_fails_closed_even_for_a_right_product(tmp_path, mode):
    result = gate(tmp_path, forge.PROOF_SQUATTER + forge.RIGHT, mode)
    assert result.status is CheckStatus.FAILED and result.detail == NO_PROOF


def test_every_run_signs_with_a_fresh_nonce_and_a_fresh_proof_path(tmp_path):
    seen = tmp_path / "seen"  # outside the run folder, so only the unsandboxed gate can write it
    probe = (
        forge.FIND_PLUGIN
        + f"open({str(seen)!r}, 'a').write(_plugin()._NONCE + ' ' + _plugin()._PROOF + '\\n')\n"
    )
    for i in range(2):
        gate(tmp_path / str(i), probe + forge.RIGHT, SandboxMode.OFF)
    (nonce1, proof1), (nonce2, proof2) = (line.split() for line in seen.read_text().splitlines())
    assert len(nonce1) == len(nonce2) == 64 and nonce1 != nonce2
    assert proof1 != proof2


# --- a product value cannot decide its own comparison (the `__eq__` hole) -----------------------


def check_of(*lines: str) -> str:
    body = "".join(f"    {line}\n" for line in lines)
    return f"import pytest\nfrom rev import reverse\n\ndef test_c():\n{body}"


@pytest.mark.parametrize(
    ("product", "check"),
    [
        (forge.ALWAYS_EQUAL, forge.CHECK),
        (forge.ALWAYS_EQUAL, check_of("assert 'ba' == reverse('ab')")),
        (forge.ALWAYS_EQUAL, check_of("assert not reverse('ab') != 'ba'")),
        (forge.ALWAYS_EQUAL, check_of("assert reverse('ab') in ('ba', 'x')")),
        (forge.ALWAYS_EQUAL, check_of("assert [reverse('ab')] == ['ba']")),
        (forge.ALWAYS_EQUAL, check_of("assert sorted([reverse('ab')]) == ['ba']")),
        (forge.ALWAYS_EQUAL, check_of("assert 'b' <= reverse('ab') < 'bb'")),
        (forge.ALWAYS_EQUAL, check_of("assert all(reverse(w) == w[::-1] for w in ['ab', 'xy'])")),
        (forge.ALWAYS_EQUAL, check_of("assert reverse('ab') == None")),
        (forge.ALWAYS_EQUAL, check_of("assert reverse('ab') == pytest.approx(1.5)")),
        (forge.ALWAYS_EQUAL, check_of("if reverse('ab') != 'ba':", "    raise AssertionError")),
        (forge.STR_ALWAYS_EQUAL, forge.CHECK),
        (forge.NESTED_ALWAYS_EQUAL, check_of("assert reverse('ab') == ['ba', ('ab',)]")),
        (forge.APPROX_ANYTHING, forge.CHECK),
        (forge.APPROX_ANYTHING, check_of("assert (reverse('ab'), 1) == ('ba', pytest.approx(1))")),
    ],
    ids=[
        "eq",
        "reflected-eq",
        "ne",
        "in",
        "inside-a-list",
        "sorted",
        "chained-order",
        "generator",
        "eq-none",
        "approx",
        "outside-an-assert",
        "str-subclass",
        "nested",
        "product-built-approx",
        "product-built-approx-in-a-tuple",
    ],
)
def test_a_value_that_equals_everything_is_failed(tmp_path, mode, product, check):
    result = gate(tmp_path, product, mode, check=check)
    assert result.status is CheckStatus.FAILED, result.detail
    assert result.detail.startswith("pytest exited 1"), result.detail


def test_a_check_module_the_guard_did_not_reach_is_never_a_pass(tmp_path, mode):
    # Stands for a pytest that stopped calling the rewrite the plugin wraps: no guard, no proof.
    check = "def test_x():\n    pass\n\ndel globals()['@boss_guard']\n"
    result = gate(tmp_path, forge.RIGHT, mode, check=check)
    assert result.status is CheckStatus.FAILED and result.detail == NO_PROOF


HONEST_COMPARISONS = """\
import collections, decimal, fractions, pytest
from rev import Poly, Trie, pair, reverse

def test_plain_values_compare_as_python_compares_them():
    assert reverse('ab') == 'ba' and reverse('ab') != 'ab'
    assert pair() == (1, 2) and pair().a == 1  # a namedtuple is still a tuple
    assert 1 == 1.0 and True == 1 and 0.1 + 0.2 == pytest.approx(0.3)
    assert [0.1 + 0.2] == pytest.approx([0.3])
    assert (len(reverse('ab')), 0.1 + 0.2) == (2, pytest.approx(0.3))
    assert collections.Counter('aab') == {'a': 2, 'b': 1}
    assert fractions.Fraction(1, 2) == 0.5 and decimal.Decimal('1.5') == 1.5
    assert 1 <= len(reverse('abc')) < 4 and 'b' in reverse('ab')
    loop = [1]
    loop.append(loop)
    assert loop[1] is loop and loop == loop

def test_product_objects_still_use_their_own_comparisons():
    assert Poly(1, 2) == Poly(1, 2) and Poly(1) != Poly(2)
    assert 'ab' in Trie(['ab']) and 'x' not in Trie(['ab'])
    assert sorted([Poly(2), Poly(1)]) == [Poly(1), Poly(2)]
"""
HONEST_PRODUCT = (
    forge.RIGHT
    + """\
import collections
pair = lambda: collections.namedtuple('Pair', 'a b')(1, 2)
class Poly:
    def __init__(self, *c): self.c = c
    def __eq__(self, other): return isinstance(other, Poly) and self.c == other.c
    def __lt__(self, other): return self.c < other.c
class Trie:
    def __init__(self, words): self.words = set(words)
    def __contains__(self, word): return word in self.words
"""
)


def test_honest_comparisons_keep_their_meaning(tmp_path, mode):
    result = gate(tmp_path, HONEST_PRODUCT, mode, check=HONEST_COMPARISONS)
    assert result.status is CheckStatus.PASSED, (result.detail, result.output_tail)
    assert result.detail == "2 passed"


# --- the proof does not touch honest checks ----------------------------------------------------

CLASS_BASED = """\
from rev import reverse

class TestReverse:
    def test_word(self):
        assert reverse('abc') == 'cba'

    def test_empty(self):
        assert reverse('') == ''
"""
PARAMETRIZED = """\
import pytest
from rev import reverse

@pytest.mark.parametrize("word", ["a", "ab", "abc", ""])
def test_twice_is_identity(word):
    assert reverse(reverse(word)) == word
"""
WITH_FIXTURES = """\
import pytest
from rev import reverse

@pytest.fixture
def word(tmp_path):
    path = tmp_path / "w"
    path.write_text("abc")
    yield path.read_text()
    path.unlink()

def test_uses_a_fixture_with_teardown(word):
    assert reverse(word) == "cba"
"""
UNITTEST_STYLE = """\
import unittest
from rev import reverse

class ReverseTest(unittest.TestCase):
    def test_word(self):
        self.assertEqual(reverse("abc"), "cba")
"""
MONKEYPATCHED = """\
from rev import reverse

def test_with_monkeypatch(monkeypatch):
    monkeypatch.setenv("X", "1")
    assert reverse("ab") == "ba"
"""


RAISES = """\
import pytest
from rev import reverse

def test_raises_inside_the_body_is_not_an_unwind():
    with pytest.raises(TypeError):
        reverse(None)
    assert reverse("ab") == "ba"
"""


@pytest.mark.parametrize(
    ("check", "count"),
    [
        (forge.CHECK, 1),
        (TWO_TESTS, 2),
        (CLASS_BASED, 2),
        (PARAMETRIZED, 4),
        (WITH_FIXTURES, 1),
        (UNITTEST_STYLE, 1),
        (MONKEYPATCHED, 1),
        (RAISES, 1),
    ],
    ids=["one", "two", "class", "parametrized", "fixtures", "unittest", "monkeypatch", "raises"],
)
def test_an_honest_check_still_passes(tmp_path, mode, check, count):
    result = gate(tmp_path, forge.RIGHT, mode, check=check)
    assert result.status is CheckStatus.PASSED, (result.detail, result.output_tail)
    assert result.detail == f"{count} passed"


def test_an_honest_check_passes_when_the_product_prints_and_logs_a_lot(tmp_path, mode):
    noisy = "import sys\nprint('x' * 100000)\nsys.stderr.write('y' * 100000)\n" + forge.RIGHT
    assert gate(tmp_path, noisy, mode).status is CheckStatus.PASSED


@pytest.mark.parametrize(
    "check",
    [
        "import pytest\n@pytest.mark.skip\ndef test_x():\n    pass\n",
        "import pytest\n@pytest.mark.xfail\ndef test_x():\n    assert False\n",
        "import pytest\ndef test_x():\n    pytest.skip('later')\n",
        FIXTURE + "    raise RuntimeError\ndef test_x(boom):\n    pass\n",
        FIXTURE + "    yield\n    raise RuntimeError\ndef test_x(boom):\n    pass\n",
        "def test_x():\n    assert False\n",
    ],
    ids=["skip", "xfail", "skip-call", "setup-error", "teardown-error", "fail"],
)
def test_a_check_that_did_not_cleanly_pass_is_still_failed(tmp_path, mode, check):
    assert gate(tmp_path, forge.RIGHT, mode, check=check).status is CheckStatus.FAILED
